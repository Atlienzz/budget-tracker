"""
eval_runner.py — Eval framework for the budget-tracker AI pipeline.

Runs labeled test cases through the email parser and bill matcher agents,
scores results using LLM-as-judge for company name matching, and saves
results to the database for display in the Streamlit dashboard.

Usage:
    python eval_runner.py           # Run full eval suite, print summary
"""

import json
import uuid
from datetime import datetime

import anthropic

import database as db
from agent_email_parser import parse_email  # returns raw dict
from agent_bill_matcher import match_bill

EVAL_DATASET_PATH = "eval_dataset.json"


# ── LLM-as-Judge ─────────────────────────────────────────────────────────────

def judge_company_match(
    extracted_company: str,
    expected_company: str,
    expected_bill_name: str,
    email_snippet: str,
) -> tuple[int, str]:
    """
    Use Claude to score how well the extracted company matches the expected one.

    Score scale:
      3 = Same company, different abbreviation or formatting
      2 = Clearly the same company with minor variation
      1 = Possibly correct but ambiguous
      0 = Wrong company or extraction failed

    Returns (score, reason).
    """
    if not extracted_company:
        return 0, "No company extracted"

    client = anthropic.Anthropic()

    prompt = f"""You are evaluating whether an AI correctly identified the company from a payment email.

Email (first 300 chars): {email_snippet[:300]}

Expected company: {expected_company}
Expected bill name: {expected_bill_name}
AI extracted: {extracted_company}

Score the match on a 0-3 scale:
3 = Same company, just different abbreviation or formatting (e.g. "AEP" vs "AEP Ohio Electric")
2 = Clearly the same company with minor variation
1 = Possibly the same company but ambiguous
0 = Wrong company or no useful extraction

Reply with ONLY: SCORE: brief reason (max 10 words)
Example: 3: AEP is clearly AEP Ohio Electric"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    # Parse "SCORE: reason"
    try:
        score_str, reason = text.split(":", 1)
        score = int(score_str.strip()[0])  # take first digit in case of leading spaces
        score = max(0, min(3, score))
        return score, reason.strip()
    except Exception:
        # Fallback: look for any digit
        for char in text:
            if char.isdigit():
                return min(3, int(char)), text
        return 0, text


# ── Single Case Runner ────────────────────────────────────────────────────────

def run_single_case(case: dict, run_id: str, pipeline_run_id: str) -> dict:
    """
    Run one eval case through parser and matcher, return a result dict.

    Does NOT call the payment recorder — eval only measures accuracy,
    it does not write payments to the database.
    """
    expected = case["expected"]

    result = {
        "run_id":               run_id,
        "case_id":              case["case_id"],
        "category":             case["category"],
        # Parser
        "expected_is_payment":  expected["is_payment_confirmation"],
        "actual_is_payment":    None,
        "parser_correct":       None,
        "expected_company":     expected.get("company") or "",
        "actual_company":       "",
        "company_judge_score":  None,
        "judge_reason":         "",
        # Amount
        "expected_amount":      expected.get("amount"),
        "actual_amount":        None,
        "amount_correct":       None,
        # Matcher
        "expected_bill_name":   expected.get("bill_name") or "",
        "actual_bill_name":     "",
        "matcher_correct":      None,
        "expected_confidence":  expected.get("confidence") or "",
        "actual_confidence":    "",
        # Overall
        "end_to_end_correct":   None,
    }

    # ── Step 1: Email parser ──────────────────────────────────────────────────
    # parse_email returns a raw dict: {is_payment_confirmation, company, amount}
    parsed = parse_email(case["body"], pipeline_run_id)

    actual_is_payment = bool(parsed.get("is_payment_confirmation", False))
    company = (parsed.get("company") or "").strip() or None
    amount  = parsed.get("amount")
    if amount is not None:
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = None

    result["actual_is_payment"] = actual_is_payment
    result["actual_company"]    = company or ""
    result["actual_amount"]     = amount
    result["parser_correct"]    = (actual_is_payment == expected["is_payment_confirmation"])

    if amount is not None and expected.get("amount") is not None:
        result["amount_correct"] = abs(amount - expected["amount"]) <= 0.01

    # ── Step 2: LLM-as-judge for company name (only when parser says payment) ─
    if actual_is_payment and company:
        score, reason = judge_company_match(
            company,
            expected.get("company") or "",
            expected.get("bill_name") or "",
            case["body"],
        )
        result["company_judge_score"] = score
        result["judge_reason"]        = reason

    # ── Step 3: Bill matcher (only when both expected + actual are payments,
    #            and we have a company name to match on) ────────────────────────
    if actual_is_payment and expected["is_payment_confirmation"] and company:
        bill_row, confidence = match_bill(company, pipeline_run_id, amount=amount)
        result["actual_confidence"] = confidence

        if bill_row is not None:
            result["actual_bill_name"] = bill_row["name"]
            result["matcher_correct"]  = (bill_row["name"] == expected.get("bill_name", ""))
        else:
            result["matcher_correct"] = False

    # ── Step 4: End-to-end correctness ───────────────────────────────────────
    if not result["parser_correct"]:
        # Parser wrong → pipeline failed
        result["end_to_end_correct"] = False
    elif not expected["is_payment_confirmation"]:
        # Correctly rejected as non-payment
        result["end_to_end_correct"] = True
    elif result["matcher_correct"] is not None:
        # Was a payment and we ran the matcher
        result["end_to_end_correct"] = result["matcher_correct"]
    else:
        # Parser correct but matcher didn't run (shouldn't happen)
        result["end_to_end_correct"] = result["parser_correct"]

    return result


# ── Metrics Calculator ────────────────────────────────────────────────────────

def calculate_metrics(results: list) -> dict:
    """Compute aggregate metrics from a list of result dicts."""
    total = len(results)

    # Parser accuracy
    parser_correct = sum(1 for r in results if r["parser_correct"])
    parser_accuracy = parser_correct / total if total else 0.0

    # True positive rate: % of actual payments correctly identified
    actual_payments = [r for r in results if r["expected_is_payment"]]
    tp = sum(1 for r in actual_payments if r["actual_is_payment"])
    tpr = tp / len(actual_payments) if actual_payments else 0.0

    # True negative rate: % of non-payments correctly filtered
    actual_non = [r for r in results if not r["expected_is_payment"]]
    tn = sum(1 for r in actual_non if not r["actual_is_payment"])
    tnr = tn / len(actual_non) if actual_non else 0.0

    # Matcher accuracy (only cases where both expected + actual are payments)
    matcher_cases = [r for r in results if r["matcher_correct"] is not None]
    matcher_correct = sum(1 for r in matcher_cases if r["matcher_correct"])
    matcher_accuracy = matcher_correct / len(matcher_cases) if matcher_cases else 0.0

    # LLM judge score average (0-3 scale)
    judge_cases = [r for r in results if r["company_judge_score"] is not None]
    avg_judge = (
        sum(r["company_judge_score"] for r in judge_cases) / len(judge_cases)
        if judge_cases else 0.0
    )

    # Confidence calibration: accuracy per confidence level
    confidence_breakdown = {}
    for conf in ["HIGH", "MEDIUM", "LOW"]:
        conf_cases = [r for r in results if r["actual_confidence"] == conf]
        if conf_cases:
            correct = sum(1 for r in conf_cases if r.get("matcher_correct"))
            confidence_breakdown[conf] = correct / len(conf_cases)
        else:
            confidence_breakdown[conf] = None

    # End-to-end
    e2e_results = [r for r in results if r["end_to_end_correct"] is not None]
    e2e_correct = sum(1 for r in e2e_results if r["end_to_end_correct"])
    e2e_accuracy = e2e_correct / len(e2e_results) if e2e_results else 0.0

    return {
        "total_cases":          total,
        "parser_accuracy":      parser_accuracy,
        "true_positive_rate":   tpr,
        "true_negative_rate":   tnr,
        "matcher_accuracy":     matcher_accuracy,
        "avg_judge_score":      avg_judge,
        "confidence_breakdown": confidence_breakdown,
        "end_to_end_accuracy":  e2e_accuracy,
    }


# ── Eval Suite Orchestrator ───────────────────────────────────────────────────

def run_eval_suite(progress_callback=None) -> tuple[str, list, dict]:
    """
    Run all test cases and return (run_id, results, metrics).

    progress_callback(i, total, case_id) is called before each case.
    """
    with open(EVAL_DATASET_PATH) as f:
        cases = json.load(f)

    run_id          = str(uuid.uuid4())[:8]
    pipeline_run_id = f"eval_{run_id}"
    results         = []

    for i, case in enumerate(cases):
        if progress_callback:
            progress_callback(i, len(cases), case["case_id"])
        result = run_single_case(case, run_id, pipeline_run_id)
        results.append(result)

    if progress_callback:
        progress_callback(len(cases), len(cases), "done")

    metrics = calculate_metrics(results)

    db.save_eval_run(run_id, metrics)
    db.save_eval_case_results(run_id, results)

    return run_id, results, metrics


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    def _progress(i, total, case_id):
        if case_id != "done":
            print(f"  [{i + 1}/{total}] {case_id}")

    print(f"\nStarting eval suite — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    run_id, results, metrics = run_eval_suite(progress_callback=_progress)

    print(f"\n{'=' * 60}")
    print(f"RUN ID: {run_id}")
    print(f"{'=' * 60}")
    print(f"Parser Accuracy:     {metrics['parser_accuracy']:.1%}  ({metrics['total_cases']} cases)")
    print(f"  True Positive Rate: {metrics['true_positive_rate']:.1%}  (payments correctly identified)")
    print(f"  True Negative Rate: {metrics['true_negative_rate']:.1%}  (non-payments correctly filtered)")
    print(f"Matcher Accuracy:    {metrics['matcher_accuracy']:.1%}")
    print(f"Avg Judge Score:     {metrics['avg_judge_score']:.2f} / 3.0")
    print(f"End-to-End:          {metrics['end_to_end_accuracy']:.1%}")

    print(f"\nConfidence Calibration:")
    for conf, acc in metrics["confidence_breakdown"].items():
        if acc is not None:
            print(f"  {conf:6s}: {acc:.1%}")
        else:
            print(f"  {conf:6s}: no cases")

    print(f"\nFailed cases:")
    failed = [r for r in results if not r["end_to_end_correct"]]
    if failed:
        for r in failed:
            print(f"  {r['case_id']:15s}  parser={'PASS' if r['parser_correct'] else 'FAIL'}  "
                  f"matcher={'PASS' if r['matcher_correct'] else ('FAIL' if r['matcher_correct'] is False else '--')}  "
                  f"company='{r['actual_company']}'  bill='{r['actual_bill_name']}'")
    else:
        print("  None -- perfect score!")

    print(f"\nResults saved to database (run_id: {run_id})")
