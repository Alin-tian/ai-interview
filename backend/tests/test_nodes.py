from types import SimpleNamespace
import pytest
from app.agents.nodes import fallback_question, fallback_evaluation, evaluate_answer, is_similar_question, plan_next


def test_question_has_topic_and_source_refs():
    session = SimpleNamespace(current_round=0, role_profile={"required_skills": ["Vue"]}, resume_profile={})
    question = fallback_question(session, [{"id": 3}])
    assert question["question"]
    assert question["source_refs"] == [3]


def test_evaluation_has_all_dimensions():
    evaluation = fallback_evaluation({"expected_points": ["取舍"]}, "我会比较方案并压测")
    assert set(evaluation["dimensions"]) == {"correctness", "completeness", "technical_depth", "project_experience", "expression", "engineering_risk_awareness"}
    assert evaluation["standard_answer_short"]
    assert evaluation["standard_answer_full"]


def test_evaluation_accepts_llm_string_fields():
    evaluation = fallback_evaluation({"expected_points": "方案取舍", "expected_evidence": "量化结果"}, "我负责方案落地，结果提升 20%。")
    assert evaluation["overall_score"] > 0


@pytest.mark.asyncio
async def test_followup_limited_to_two():
    assert await plan_next({}, {"overall_score": 40}, 0, 1, 10) == "followup"
    assert await plan_next({}, {"overall_score": 40}, 2, 1, 10) == "new_question"
    assert await plan_next({}, {"overall_score": 90}, 0, 10, 10) == "finish"


def test_near_duplicate_questions_are_rejected():
    asked = ["请介绍一个与目标岗位相关的真实项目，并说明你的职责和结果。"]
    assert is_similar_question("请介绍一个真实项目，说明职责、行动和结果", asked)
    assert not is_similar_question("资源不足时你如何调整方案并验证效果？", asked)


def test_fallback_score_uses_evidence_not_length_only():
    question = {"expected_points": ["背景", "结果"], "expected_evidence": ["项目名称", "个人行动"]}
    weak = fallback_evaluation(question, "我觉得这个方案很好。" )
    strong = fallback_evaluation(question, "在支付项目中我负责改造流程，首先分析失败率，其次增加监控和灰度验证，最终将失败率从 3% 降到 1%，并复盘风险边界。")
    assert strong["overall_score"] > weak["overall_score"]
    assert strong["evidence_found"]


@pytest.mark.asyncio
async def test_evaluation_normalises_malformed_model_fields(monkeypatch):
    async def malformed_model(*_args):
        return {"strengths": "有项目经验", "evidence_gaps": 3, "factual_errors": 0, "improvement_suggestion": 42}

    monkeypatch.setattr("app.agents.nodes.ask_json", malformed_model)
    result = await evaluate_answer({"expected_points": ["取舍"]}, "我负责项目并完成验证")

    assert result["strengths"] == ["有项目经验"]
    assert result["evidence_gaps"] == ["3"]
    assert result["factual_errors"] == ["0"]
    assert isinstance(result["improvement_suggestion"], str)
