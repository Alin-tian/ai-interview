import hashlib
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.interview import InterviewSession, InterviewSource, InterviewTurn, InterviewQAMessage
from app.crawlers.web_sources import fetch_public_page, search_public_sources
from app.agents.nodes import analyze_resume, analyze_role, generate_question, evaluate_answer, plan_next, final_review
from app.rag.material_retriever import retriever


async def sources_for(session_id: int, db: AsyncSession) -> list[InterviewSource]:
    result = await db.execute(select(InterviewSource).where(InterviewSource.session_id == session_id).order_by(InterviewSource.id))
    return list(result.scalars())


def source_dict(source: InterviewSource) -> dict:
    return {"id": source.id, "title": source.title, "url": source.url, "content": source.content, "source_type": source.source_type}


async def add_source(
    db: AsyncSession, session_id: int, source_type: str, title: str, url: str,
    content: str, status: str = "ready",
) -> bool:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    existing = await db.execute(select(InterviewSource).where(InterviewSource.session_id == session_id, InterviewSource.content_hash == digest))
    if existing.scalar_one_or_none():
        return False
    source = InterviewSource(
        session_id=session_id, source_type=source_type, title=title[:512],
        url=url[:2048], content=content[:12000], content_hash=digest, status=status,
    )
    db.add(source)
    await db.flush()
    try:
        await retriever.index_source(session_id, source.id, source_type, source.title, source.content)
    except RuntimeError:
        await db.rollback()
        raise
    return True


async def collect_sources(session: InterviewSession, db: AsyncSession, urls: list[str] | None = None) -> dict:
    added, failures = 0, []
    for url in urls or []:
        try:
            page = await fetch_public_page(url)
            added += await add_source(db, session.id, "user_url", page["title"], page["url"], page["content"])
        except Exception as exc:
            failures.append(str(exc))
    try:
        results = await search_public_sources(f"{session.job_title} 面试题 职位要求")
        for result in results:
            try:
                page = await fetch_public_page(result["url"])
                added += await add_source(db, session.id, "web_question", page["title"], page["url"], page["content"])
            except Exception as exc:
                # A search result is still useful and attributable when a site
                # blocks crawling or returns non-HTML.  Persist Tavily's public
                # snippet instead of silently dropping the result.
                fallback_content = str(result.get("raw_content") or result.get("snippet") or "").strip()
                if fallback_content:
                    try:
                        added += await add_source(
                            db, session.id, "web_search_result", result.get("title", "公开搜索结果"),
                            result["url"], fallback_content, status="summary_only",
                        )
                    except Exception as save_exc:
                        failures.append(f"保存搜索摘要失败：{save_exc}")
                failures.append(f"未抓取网页正文：{result.get('url')}（{exc}）")
    except Exception as exc:
        failures.append(f"公开搜索不可用: {exc}")
    await db.commit()
    return {"added": added, "failures": failures}


async def initialize(session: InterviewSession, db: AsyncSession) -> InterviewTurn:
    sources = [source_dict(x) for x in await sources_for(session.id, db)]
    await add_source(db, session.id, "resume", session.resume_file_name, "", session.resume_text)
    await add_source(db, session.id, "jd", f"{session.job_title} JD", "", session.job_description)
    await db.commit()
    sources = [source_dict(x) for x in await sources_for(session.id, db)]
    session.resume_profile = await analyze_resume(session.resume_text)
    session.role_profile = await analyze_role(session.job_title, session.company, session.job_description, sources)
    question = await generate_question(session, sources, previous_questions=[])
    turn = InterviewTurn(session_id=session.id, round_no=1, is_followup=False, question=question)
    session.current_round, session.followups_for_round, session.status = 1, 0, "in_progress"
    session.updated_at = datetime.utcnow()
    db.add(turn)
    await db.commit()
    await db.refresh(turn)
    return turn


async def evaluate_turn(session: InterviewSession, turn: InterviewTurn, answer: str, db: AsyncSession) -> tuple[dict, str]:
    evaluation = await evaluate_answer(turn.question, answer)
    action = await plan_next(turn.question, evaluation, session.followups_for_round, session.current_round, session.max_rounds)
    turn.answer, turn.evaluation = answer, evaluation
    session.updated_at = datetime.utcnow()
    await db.commit()
    return evaluation, action


async def advance_interview(session: InterviewSession, turn: InterviewTurn, action: str, db: AsyncSession) -> tuple[InterviewTurn | None, dict | None]:
    next_turn, review = None, None
    sources = await retrieve_context(session, db, turn.question.get("question", ""))
    existing = await db.execute(select(InterviewTurn).where(InterviewTurn.session_id == session.id).order_by(InterviewTurn.id))
    previous_questions = [x.question.get("question", "") for x in existing.scalars() if x.question]
    if action == "followup":
        session.followups_for_round += 1
        question = await generate_question(session, sources, is_followup=True, previous_questions=previous_questions)
        next_turn = InterviewTurn(session_id=session.id, round_no=session.current_round, is_followup=True, question=question)
        db.add(next_turn)
    elif action == "new_question":
        session.current_round += 1
        session.followups_for_round = 0
        question = await generate_question(session, sources, previous_questions=previous_questions)
        next_turn = InterviewTurn(session_id=session.id, round_no=session.current_round, is_followup=False, question=question)
        db.add(next_turn)
    else:
        result = await db.execute(select(InterviewTurn).where(InterviewTurn.session_id == session.id))
        # turn 已经属于查询结果，不能重复加入，否则最后一题会被重复计分。
        turns = list(result.scalars())
        review = await final_review(turns, session.role_profile)
        session.final_review, session.status, session.finished_at = review, "completed", datetime.utcnow()
    session.updated_at = datetime.utcnow()
    await db.commit()
    if next_turn:
        await db.refresh(next_turn)
    return next_turn, review


async def delete_session_files(session: InterviewSession) -> None:
    Path(session.resume_path).unlink(missing_ok=True)


async def retrieve_context(session: InterviewSession, db: AsyncSession, query: str) -> list[dict]:
    source_rows = {x.id: x for x in await sources_for(session.id, db)}
    try:
        hits = await retriever.search(session.id, query)
    except Exception:
        # Retrieval enriches question generation but must not block the
        # interview. Fall back to the persisted resume/JD/public materials.
        return [
            {
                "id": source.id,
                "title": source.title,
                "content": source.content,
                "url": source.url,
                "source_type": source.source_type,
            }
            for source in list(source_rows.values())[:5]
        ]
    return [{"id": x["source_id"], "title": x["title"], "content": x["content"], "url": source_rows.get(x["source_id"]).url if source_rows.get(x["source_id"]) else "", "source_type": "retrieved"} for x in hits]
