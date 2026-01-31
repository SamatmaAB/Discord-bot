import asyncio

# Mock data based on the actual API response observed
MOCK_API_RESPONSE = {
    "success": True,
    "data": [
        {"pos": 5, "name": "People's Education Society University - PESU1", "score": 660},
        {"pos": 13, "name": "People's Education Society University - PESU2", "score": 660}
    ]
}

# The problematic function from bot.py (simplified for testing)
async def extract_team_positions_original(my_team, rival_team):
    result = {}
    targets = {my_team.lower(): my_team, rival_team.lower(): rival_team}
    
    entries = MOCK_API_RESPONSE.get("data", [])
    
    for entry in entries:
        # ORIGINAL BROKEN LOGIC:
        team_obj = entry.get("team", {})
        raw_name = str(team_obj.get("name", "")).strip()
        
        key = raw_name.lower()
        if key in targets:
            result[targets[key]] = {
                "rank": entry.get("pos") or entry.get("rank"),
                "score": entry.get("score")
            }
            
    return result

# The proposed fixed function
async def extract_team_positions_fixed(my_team, rival_team):
    result = {}
    targets = {my_team.lower(): my_team, rival_team.lower(): rival_team}
    
    entries = MOCK_API_RESPONSE.get("data", [])
    for entry in entries:
        # FIXED LOGIC:
        raw_name = entry.get("team", {}).get("name") or entry.get("name")
        raw_name = str(raw_name).strip() if raw_name else ""
        
        key = raw_name.lower()
        if key in targets:
            result[targets[key]] = {
                "rank": entry.get("pos") or entry.get("rank"),
                "score": entry.get("score")
            }
            
    return result

async def main():
    MY_TEAM = "People's Education Society University - PESU2"
    RIVAL_TEAM = "People's Education Society University - PESU1"
    
    print("--- Testing Original Logic ---")
    results = await extract_team_positions_original(MY_TEAM, RIVAL_TEAM)
    print(f"Found teams: {list(results.keys())}")
    if not results:
        print("FAILED: Original logic found no teams (Expected behavior for reproduction)")
    
    print("\n--- Testing Fixed Logic ---")
    results = await extract_team_positions_fixed(MY_TEAM, RIVAL_TEAM)
    print(f"Found teams: {list(results.keys())}")
    if len(results) == 2:
        print("SUCCESS: Fixed logic found both teams")
    else:
        print("FAILED: Fixed logic did not find all teams")

if __name__ == "__main__":
    asyncio.run(main())
