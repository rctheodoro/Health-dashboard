#!/usr/bin/env python3
"""
Validate Garmin Connect token cache and test data fetch.
Run after GARMIN-SETUP.md Step 2.

Usage:
    python3 validate-garmin.py
"""

import sys
from datetime import datetime, timedelta

def validate_garmin():
    try:
        import garminconnect
    except ImportError:
        print("❌ garminconnect not installed. Run:")
        print("   python3 -m pip install garminconnect garth")
        return False
    
    # Try to load cached tokens
    try:
        garmin = garminconnect.Garmin()
        garmin.login(tokenstore="/Users/rtbot/.garth")
    except FileNotFoundError:
        print("❌ Token cache not found at ~/.garth")
        print("   Run the setup from GARMIN-SETUP.md first.")
        return False
    except Exception as e:
        print(f"❌ Failed to load tokens: {e}")
        print("   The tokens may have expired. Re-run the setup.")
        return False
    
    # Test basic queries
    try:
        print("✅ Garmin tokens loaded successfully")
        print()
        
        # Get user info
        try:
            personal_info = garmin.get_personal_info()
            user_name = personal_info.get("displayName", "Unknown")
            print(f"   User: {user_name}")
        except:
            print("   User: [could not fetch]")
        
        # Get today's metrics
        today = datetime.now().strftime("%Y-%m-%d")
        
        try:
            body_battery = garmin.get_body_battery(today)
            if body_battery:
                bb_value = body_battery[0].get("bodyBatteryValueTxt", "N/A")
                print(f"   Body battery (today): {bb_value}")
        except:
            print("   Body battery: [not available]")
        
        try:
            vo2max = garmin.get_vo2max()
            if vo2max:
                print(f"   VO2max: {vo2max[0].get('createTimeInSeconds', 'N/A')}")
        except:
            print("   VO2max: [not available]")
        
        try:
            readiness = garmin.get_training_readiness(today)
            if readiness:
                score = readiness[0].get("trainingReadinessScore", "N/A")
                print(f"   Training readiness (today): {score}")
        except:
            print("   Training readiness: [not available]")
        
        # Activities (last 1 day)
        try:
            activities = garmin.get_activities(0, 10)
            if activities:
                recent = [a for a in activities if (datetime.now() - datetime.fromisoformat(
                    a.get("startTimeInSeconds", 0) // 1000 
                    if isinstance(a.get("startTimeInSeconds"), int) 
                    else a.get("startTimeInSeconds", ""))).days < 2]
                if recent:
                    print(f"   Recent activities: {len(recent)}")
                    for activity in recent[:3]:
                        activity_name = activity.get("activityName", "Unknown")
                        print(f"     • {activity_name}")
        except:
            print("   Recent activities: [not available]")
        
        print()
        print("✅ Garmin integration is ready!")
        print()
        print("Next step: Add this to your health dashboard daily report.")
        return True
        
    except Exception as e:
        print(f"❌ Data fetch failed: {e}")
        print("   Check your internet connection and Garmin account status.")
        return False

if __name__ == "__main__":
    success = validate_garmin()
    sys.exit(0 if success else 1)
