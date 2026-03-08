from agent_bill_matcher import match_bill

# Should match a real bill with HIGH confidence
bill, confidence = match_bill("Xfinity")
print(f'Test 1: {bill["name"] if bill is not None else None} — {confidence}')

# Should match with HIGH confidence
bill, confidence = match_bill("Lending Club")
print(f'Test 2: {bill["name"] if bill is not None else None} — {confidence}')

# Should come back LOW — retail store
bill, confidence = match_bill("Amazon")
print(f'Test 3: {bill["name"] if bill is not None else None} — {confidence}')
