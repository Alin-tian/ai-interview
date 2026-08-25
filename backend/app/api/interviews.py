import asyncio
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import delete, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.database import get_db
from app.models.interview import InterviewSession, InterviewSource, InterviewTurn, InterviewQAMessage
from app.services.resume_parser import save_and_parse_pdf
from app.services.interview_service import collect_sources, initialize, evaluate_turn, advance_interview, sources_for, source_dict, delete_session_files, retrieve_context
from app.services.cache import acquire_answer_lock, delete_session_cache, release_answer_lock
from app.agents.nodes import plan_next
from app.rag.material_retriever import retriever
from app.utils.sse import event, node_enter, node_leave

router = APIRouter(prefix="/interviews", tags=["interviews"])
settings = get_settings()


async def session_or_404(session_id: int, db: AsyncSession) -> InterviewSession:
    result = await db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "面试会话不存在")
    return session


def serialize_turn(turn: InterviewTurn) -> dict:
    question = turn.question or {}
    return {"id": turn.id, "round_no": turn.round_no, "phase": question.get("phase"), "phase_label": question.get("phase_label"), "is_followup": turn.is_followup, "question": question, "answer": turn.answer, "evaluation": turn.evaluation}


@router.post("")
async def create_interview(
    resume_pdf: UploadFile = File(...), job_title: str = Form(...), company: str = Form(""),
    job_description: str = Form(...), source_urls: str = Form("[]"), db: AsyncSession = Depends(get_db),
):
    if not job_title.strip() or not job_description.strip():
        raise HTTPException(422, "岗位名称和 JD 为必填项")
    try:
        urls = json.loads(source_urls or "[]")
        if not isinstance(urls, list): raise ValueError()
    except ValueError:
        raise HTTPException(422, "source_urls 必须是 JSON 字符串数组")
    try:
        path, text = await save_and_parse_pdf(resume_pdf, settings.upload_dir)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    session = InterviewSession(job_title=job_title.strip(), company=company.strip(), job_description=job_description.strip(), resume_file_name=resume_pdf.filename or "resume.pdf", resume_path=path, resume_text=text)
    db.add(session)
    await db.commit(); await db.refresh(session)
    session_id, status = session.id, session.status
    collection = await collect_sources(session, db, urls)
    await db.refresh(session)
    return {"session_id": session.id, "status": session.status, "source_collection": collection, "notice": "公开网页资料仅供参考；未配置搜索服务时仅使用用户提供资料、简历和 JD。"}


@router.post("/{session_id}/sources/refresh")
async def refresh_sources(session_id: int, urls: list[str] | None = None, db: AsyncSession = Depends(get_db)):
    session = await session_or_404(session_id, db)
    return await collect_sources(session, db, urls)


@router.post("/{session_id}/start")
async def start_interview(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await session_or_404(session_id, db)
    async def stream():
        if session.status == "completed":
            yield event("workflow_error", {"error": "本场面试已结束"}); return
        result = await db.execute(select(InterviewTurn).where(InterviewTurn.session_id == session.id).order_by(InterviewTurn.id))
        existing = result.scalars().first()
        if existing:
            yield event("question", serialize_turn(existing)); return
        yield node_enter("resume_analyzer", "简历分析 Agent")
        try:
            turn = await initialize(session, db)
        except RuntimeError as exc:
            await db.rollback()
            yield event("workflow_error", {"error": str(exc)})
            return
        yield node_leave("resume_analyzer", "简历分析 Agent")
        yield event("question", serialize_turn(turn))
    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/{session_id}/answer")
async def submit_answer(session_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    session = await session_or_404(session_id, db)
    if session.status == "completed":
        raise HTTPException(409, "本场面试已完成，不能继续提交回答")
    answer, turn_id = str(payload.get("answer", "")).strip(), payload.get("turn_id")
    if not turn_id: raise HTTPException(422, "turn_id 为必填项")
    result = await db.execute(select(InterviewTurn).where(InterviewTurn.id == int(turn_id), InterviewTurn.session_id == session.id))
    turn = result.scalar_one_or_none()
    if not turn: raise HTTPException(409, "题目不存在")
    if turn.answer:
        # Recovery path: evaluation may have committed before next-question
        # generation failed. Reuse the persisted answer/evaluation.
        later = (await db.execute(select(InterviewTurn).where(
            InterviewTurn.session_id == session.id,
            InterviewTurn.id > turn.id,
        ).order_by(InterviewTurn.id))).scalars().first()
        if later:
            async def existing_stream():
                yield event("question", serialize_turn(later))
            return StreamingResponse(existing_stream(), media_type="text/event-stream")
        answer = turn.answer
        evaluation = turn.evaluation or {}
        action = await plan_next(turn.question, evaluation, session.followups_for_round, session.current_round, session.max_rounds)
        resume_only = True
    else:
        if not answer: raise HTTPException(422, "answer 为必填项")
        resume_only = False
    if not resume_only and not await acquire_answer_lock(session.id, turn.id):
        raise HTTPException(409, "该题正在处理，请勿重复提交")
    async def stream():
        nonlocal evaluation, action
        try:
            if not resume_only:
                yield node_enter("answer_evaluator", "回答评估 Agent")
                evaluation_task = asyncio.create_task(evaluate_turn(session, turn, answer, db))
                try:
                    # Keep the SSE connection alive while the model is evaluating.
                    # Browser/proxy idle timeouts otherwise surface as a misleading
                    # `network error` even though the request is still progressing.
                    while not evaluation_task.done():
                        done, _ = await asyncio.wait({evaluation_task}, timeout=10)
                        if not done:
                            yield ": keep-alive\n\n"
                    evaluation, action = await evaluation_task
                except asyncio.CancelledError:
                    # A disconnected browser must not cancel evaluation after the
                    # answer has been accepted. Finish both persistence and the
                    # next-step transition; a reopened historical session can then
                    # continue from the generated question without resubmission.
                    evaluation, action = await asyncio.shield(evaluation_task)
                    try:
                        await asyncio.shield(advance_interview(session, turn, action, db))
                    except Exception:
                        await db.rollback()
                    return
                except Exception as exc:
                    await db.rollback()
                    yield event("workflow_error", {"error": f"回答评估失败：{exc}"})
                    return
                yield node_leave("answer_evaluator", "回答评估 Agent")
                # Include the accepted answer so the client can render the completed
                # turn immediately, without waiting for next-question generation.
                yield event("evaluation", {"turn_id": turn.id, "answer": answer, "evaluation": evaluation})
            yield node_enter("next_step", "生成下一题或面试总评")
            try:
                next_turn, review = await advance_interview(session, turn, action, db)
            except Exception as exc:
                await db.rollback()
                yield event("workflow_error", {"error": f"后续面试流程失败：{exc}"})
                return
            yield node_leave("next_step", "生成下一题或面试总评")
            if next_turn: yield event("question", serialize_turn(next_turn))
            if review: yield event("interview_completed", review)
        finally:
            # StreamingResponse can be cancelled when the browser disconnects.
            # Cancellation is not an Exception on modern Python, so cleanup must
            # live in finally or the Redis lock remains until its TTL expires.
            if not resume_only:
                await release_answer_lock(session.id, turn.id)
    cleanup = None if resume_only else BackgroundTask(release_answer_lock, session.id, turn.id)
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=cleanup,
    )


@router.post("/{session_id}/ask")
async def ask(session_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    session = await session_or_404(session_id, db)
    question = str(payload.get("question", "")).strip()
    if not question: raise HTTPException(422, "question 为必填项")
    sources = await retrieve_context(session, db, question)
    context = "\n".join(x["content"][:800] for x in sources[:4])
    answer = f"基于本场面试资料，可优先围绕以下岗位能力梳理：{session.role_profile.get('required_skills', [])[:5]}。\n\n你的问题：{question}\n\n相关上下文摘要：{context[:1800]}\n\n公开网页资料仅供参考，请以真实项目经历和岗位要求为准。"
    citations = [{"title": x.get("title", "资料"), "url": x.get("url", "")} for x in sources if x.get("url")][:3]
    db.add_all([InterviewQAMessage(session_id=session.id, role="user", content=question), InterviewQAMessage(session_id=session.id, role="assistant", content=answer, citations=citations)])
    session.updated_at = datetime.utcnow()
    await db.commit()
    return {"answer": answer, "citations": citations}


@router.get("/history/list")
async def history(db: AsyncSession = Depends(get_db)):
    sessions = (await db.execute(select(InterviewSession).order_by(desc(InterviewSession.updated_at), desc(InterviewSession.created_at)))).scalars().all()
    return {"data": [{"id": x.id, "job_title": x.job_title, "company": x.company, "status": x.status, "current_round": x.current_round, "created_at": x.created_at.isoformat(), "updated_at": (x.updated_at or x.created_at).isoformat(), "overall_score": (x.final_review or {}).get("overall_score")} for x in sessions]}


@router.get("/{session_id}")
async def get_interview(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await session_or_404(session_id, db)
    turns = (await db.execute(select(InterviewTurn).where(InterviewTurn.session_id == session.id).order_by(InterviewTurn.id))).scalars().all()
    messages = (await db.execute(select(InterviewQAMessage).where(InterviewQAMessage.session_id == session.id).order_by(InterviewQAMessage.id))).scalars().all()
    sources = await sources_for(session.id, db)
    review = session.final_review or {}
    phase = (turns[-1].question or {}).get("phase") if turns else "background"
    return {"data": {"id": session.id, "job_title": session.job_title, "company": session.company, "status": session.status, "phase": phase, "phase_label": (turns[-1].question or {}).get("phase_label") if turns else "背景与经历核验", "current_round": session.current_round, "max_rounds": session.max_rounds, "role_profile": session.role_profile or {}, "capability_scores": review.get("capability_scores", {}), "coverage": review.get("coverage", 0), "degraded_mode": any((t.evaluation or {}).get("degraded") for t in turns), "degraded_reasons": ["模型不可用，使用规则化评估"] if any((t.evaluation or {}).get("degraded") for t in turns) else [], "workflow_status": "completed" if session.status == "completed" else "in_progress", "final_review": session.final_review, "turns": [serialize_turn(x) for x in turns], "sources": [{"id": x.id, "title": x.title, "url": x.url, "source_type": x.source_type, "status": x.status} for x in sources], "qa_messages": [{"role": x.role, "content": x.content, "citations": x.citations} for x in messages]}}


@router.delete("/{session_id}")
async def delete_interview(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await session_or_404(session_id, db)
    # These stores are outside the database transaction. Clear them before the
    # database row, so a transient failure keeps the session available to retry.
    await retriever.delete_session(session.id)
    await delete_session_cache(session.id)
    await delete_session_files(session)
    try:
        # Explicit deletes do not depend on foreign-key cascading being enabled.
        await db.execute(delete(InterviewQAMessage).where(InterviewQAMessage.session_id == session.id))
        await db.execute(delete(InterviewSource).where(InterviewSource.session_id == session.id))
        await db.execute(delete(InterviewTurn).where(InterviewTurn.session_id == session.id))
        await db.delete(session)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"message": "会话已删除"}
