import re
from difflib import SequenceMatcher
from app.agents.engine import ask_json

PHASES = [("background", "背景与经历核验"), ("capability", "岗位核心能力"), ("scenario", "项目与工作情景"), ("followup", "回答质量追问")]
DIMENSIONS = ["correctness", "completeness", "technical_depth", "project_experience", "expression", "engineering_risk_awareness"]

def _terms(text: str, limit: int = 12) -> list[str]:
    return list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{1,}|[\u4e00-\u9fff]{2,}", text or "")))[:limit]

def _list_of_strings(value) -> list[str]:
    """Normalise imperfect LLM JSON fields before business logic uses them."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, (str, int, float)) and str(item).strip()]
    return []

def _normalise_question(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", value or "").lower()

def is_similar_question(candidate: str, previous_questions: list[str], threshold: float = 0.72) -> bool:
    candidate = _normalise_question(candidate)
    if not candidate: return True
    for previous in previous_questions:
        prior = _normalise_question(previous)
        if prior and (candidate == prior or candidate in prior or prior in candidate or SequenceMatcher(None, candidate, prior).ratio() >= threshold): return True
    return False

async def analyze_resume(resume_text: str) -> dict:
    fallback = {"projects": [], "skills": _terms(resume_text), "highlights": [], "deep_dive_points": _terms(resume_text, 6)}
    data = await ask_json("提取简历中的项目、职责、技能和可追问证据。只输出 JSON: projects, skills, highlights, deep_dive_points。不得编造。", resume_text[:12000])
    return {**fallback, **(data or {})}

async def analyze_role(job_title: str, company: str, jd: str, sources: list[dict]) -> dict:
    fallback = {"role_type": job_title, "required_skills": _terms(jd), "optional_skills": [], "capabilities": [{"name": x, "weight": 1} for x in DIMENSIONS], "topics": _terms(jd, 8), "notes": ["公开资料仅作参考"]}
    context = "\n".join(s.get("content", "")[:1200] for s in sources[:5])
    data = await ask_json("分析岗位 JD，输出 JSON: role_type, required_skills, optional_skills, capabilities([{name,weight}]), topics, notes。能力维度必须来自 JD，不得把公开网页当内部事实。", f"岗位:{job_title}\n公司:{company}\nJD:{jd}\n公开资料:{context}")
    return {**fallback, **(data or {})}

def phase_for_round(round_no: int, is_followup: bool = False) -> tuple[str, str]:
    if is_followup: return PHASES[3]
    return PHASES[min(max(round_no - 1, 0), 2)]

def fallback_question(session, sources: list[dict], is_followup: bool = False, variant: int = 0) -> dict:
    phase, label = phase_for_round(session.current_round or 1, is_followup)
    skills = (session.role_profile or {}).get("required_skills", []) or (session.resume_profile or {}).get("skills", [])
    focus = "、".join(skills[:3]) or "岗位核心能力"
    prompts = {
        "background": [f"请介绍一个与目标岗位相关、能体现 {focus} 的真实经历：你的职责、行动与结果分别是什么？", f"从简历中选择一个最有代表性的项目，说明它为何与 {focus} 相关，以及你个人做出的关键贡献。"],
        "capability": [f"围绕 {focus}，请说明你会如何拆解一项工作任务，并解释方案取舍和验证标准。", f"岗位要求涉及 {focus}。请用一个真实场景说明你如何判断优先级、推进协作并交付结果。"],
        "scenario": [f"假设负责的工作出现目标未达成或资源受限，你会如何运用 {focus} 定位问题、调整方案并验证效果？", "请描述一次复杂问题处理经历：背景、可选方案、最终取舍、风险控制和复盘分别是什么？"],
        "followup": ["针对刚才的回答，请给出一个可验证的结果指标，并说明指标不达预期时的排查和止损动作。", "你刚才提到了方案选择。请进一步说明被放弃方案的风险、边界条件，以及如何证明当前方案更合适。"],
    }
    text = prompts[phase][variant % len(prompts[phase])]
    web_sources = [source for source in sources if source.get("source_type") in {"user_url", "web_question", "retrieved"}]
    selected_sources = web_sources or sources
    if selected_sources and phase != "followup":
        source = selected_sources[0]
        topic = _terms(source.get("content", ""), 3)
        if topic:
            text += f" 请结合公开资料《{source.get('title', '资料')}》中涉及的“{'、'.join(topic)}”说明你的判断。"
    return {"phase": phase, "phase_label": label, "category": focus, "difficulty": "medium", "question": text, "expected_points": ["真实背景与职责", "关键决策与取舍", "结果指标或验证方式"], "expected_evidence": ["项目名称或场景", "个人行动", "可验证结果"], "source_refs": [s["id"] for s in sources[:3] if "id" in s], "is_followup": is_followup}

async def generate_question(session, sources: list[dict], is_followup: bool = False, previous_questions: list[str] | None = None) -> dict:
    previous_questions = previous_questions or []
    fallback = fallback_question(session, sources, is_followup, len(previous_questions))
    phase, label = phase_for_round(session.current_round or 1, is_followup)
    web_sources = [source for source in sources if source.get("source_type") in {"user_url", "web_question", "retrieved"}]
    sources = web_sources + [source for source in sources if source not in web_sources]
    data = await ask_json("你是严谨的中文面试官。基于简历和 JD 生成一题。严禁重复或改写已问题，必须切换考察角度。只输出 JSON: phase,phase_label,category,difficulty,question,expected_points,expected_evidence,source_refs。不得编造候选人经历或公司内部信息。", f"阶段:{label}\n简历:{session.resume_text[:6000]}\nJD:{session.job_description[:4000]}\n已问问题（不可重复）:{previous_questions[-8:]}\n资料:{[{ 'id':x.get('id'),'content':x.get('content','')[:600]} for x in sources[:5]]}")
    if not data or not data.get("question") or is_similar_question(data["question"], previous_questions): return fallback
    data["expected_points"] = _list_of_strings(data.get("expected_points")) or fallback["expected_points"]
    data["expected_evidence"] = _list_of_strings(data.get("expected_evidence")) or fallback["expected_evidence"]
    if not isinstance(data.get("source_refs"), list):
        data["source_refs"] = fallback["source_refs"]
    return {**fallback, **data, "phase": phase, "phase_label": label, "is_followup": is_followup}

def fallback_evaluation(question: dict, answer: str) -> dict:
    text = answer.strip()
    expected_points = _list_of_strings(question.get("expected_points"))
    expected_evidence = _list_of_strings(question.get("expected_evidence"))
    expected = " ".join(expected_points + expected_evidence)
    evidence = bool(re.search(r"\d|%|项目|客户|团队|负责|结果|数据|指标", text)); structure = len(re.findall(r"首先|其次|最后|背景|行动|结果|因此|因为", text)) >= 2; risk = bool(re.search(r"风险|验证|复盘|监控|异常|取舍|边界", text))
    relevance = min(25, 10 + sum(term in text for term in _terms(expected, 8)) * 4); evidence_score = 30 if evidence else 10; structure_score = 20 if structure else 8; risk_score = 15 if risk else 5; clarity = 10 if len(text) >= 40 else 4
    score = relevance + evidence_score + structure_score + risk_score + clarity
    dimensions = {"correctness": relevance + 5, "completeness": structure_score + 5, "technical_depth": risk_score + 5, "project_experience": evidence_score, "expression": clarity * 2, "engineering_risk_awareness": risk_score + 5}
    return {"overall_score": score, "dimensions": dimensions, "dimension_scores": dimensions, "strengths": ["回答包含可识别的经历证据"] if evidence else [], "evidence_found": ["回答中的项目或结果证据"] if evidence else [], "evidence_gaps": [] if evidence else question.get("expected_evidence", []), "missing_points": [] if structure else question.get("expected_points", []), "factual_errors": [], "risk_flags": [] if risk else ["未说明风险或验证方式"], "improvement_suggestion": "请补充真实背景、个人行动、量化结果和验证方式。", "reference_answer": "按背景、行动、取舍、结果、复盘的结构回答。", "source_refs": question.get("source_refs", []), "degraded": True, "next_action": "new_question"}

def _calibrate_evaluation(result: dict, fallback: dict) -> dict:
    raw = result.get("dimension_scores") or result.get("dimensions") or fallback["dimensions"]
    dimensions = {k: max(0, min(100, int(raw.get(k, fallback["dimensions"][k])))) for k in DIMENSIONS}
    weights = [0.2, 0.2, 0.15, 0.2, 0.1, 0.15]
    score = round(sum(dimensions[k] * w for k, w in zip(DIMENSIONS, weights)))
    # Prevent malformed model output (for example an unexplained 0-8) from
    # overwhelming an otherwise evidence-rich answer.
    if result.get("evidence_found"):
        score = max(score, min(50, fallback["overall_score"] // 2))
    else:
        score = min(score, 59)
    score = max(score, 20 if result.get("evidence_found") else 10)
    if len(result.get("factual_errors") or []) >= 2: score = min(score, 49)
    result.update(dimensions=dimensions, dimension_scores=dimensions, overall_score=score)
    return result

async def evaluate_answer(question: dict, answer: str) -> dict:
    fallback = fallback_evaluation(question, answer)
    data = await ask_json("严谨评估候选人回答。区分事实错误、证据不足和合理的不同实现。每项维度 0-100，评分必须与 evidence_found 对应；没有证据不得超过 59 分。只输出 JSON: dimensions,evidence_found,evidence_gaps,strengths,missing_points,factual_errors,risk_flags,improvement_suggestion,reference_answer。", f"问题:{question}\n回答:{answer[:10000]}")
    if not data: return fallback
    return _calibrate_evaluation({**fallback, **data, "degraded": False}, fallback)

async def plan_next(question: dict, evaluation: dict, followups: int, current_round: int, max_rounds: int) -> str:
    if current_round >= max_rounds: return "finish"
    if followups < 2 and evaluation.get("overall_score", 0) < 65: return "followup"
    return "new_question"

async def final_review(turns: list, role_profile: dict | None = None) -> dict:
    evaluated = [t.evaluation for t in turns if t.evaluation]
    if not evaluated: return {"overall_score": 0, "summary": "尚未完成有效回答", "weak_points": [], "study_plan": [], "capability_scores": {}, "coverage": 0, "disclaimer": "仅基于本次模拟回答，不代表真实招聘结论。"}
    values = {k: [x.get("dimension_scores", {}).get(k, 0) for x in evaluated] for k in DIMENSIONS}
    return {"overall_score": round(sum(x.get("overall_score", 0) for x in evaluated) / len(evaluated)), "summary": "本报告基于本次模拟回答和岗位要求生成，不代表真实招聘结论。", "weak_points": list(dict.fromkeys(i for x in evaluated for i in x.get("missing_points", [])))[:5], "study_plan": ["针对薄弱能力补充一个真实项目案例", "使用背景—行动—结果—复盘结构练习表达"], "capability_scores": {k: round(sum(v) / len(v)) for k, v in values.items()}, "coverage": round(len(evaluated) / max(len(turns), 1) * 100), "risk_flags": list(dict.fromkeys(i for x in evaluated for i in x.get("risk_flags", []))), "disclaimer": "仅基于本次模拟回答，不代表真实招聘结论。", "turns_scored": len(evaluated)}
