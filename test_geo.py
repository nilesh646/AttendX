import math

def test_attendance_geo(teacher_lat, teacher_lng, student_lat, student_lng, student_accuracy, allowed_radius=50):
    print(f"\n--- Testing Check-In ---")
    print(f"Teacher Location: {teacher_lat}, {teacher_lng} (Radius: {allowed_radius}m)")
    print(f"Student Location: {student_lat}, {student_lng} (Accuracy: {student_accuracy}m)")
    
    # 1. Haversine Math (Calculating Distance)
    R = 6371000 # Earth radius in meters
    dlat = math.radians(student_lat - teacher_lat)
    dlng = math.radians(student_lng - teacher_lng)
    
    a = (math.sin(dlat/2)**2 + 
         math.cos(math.radians(teacher_lat)) * math.cos(math.radians(student_lat)) * math.sin(dlng/2)**2)
    
    distance = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    geo_distance = int(distance)
    
    # 2. Verdict Logic
    if geo_distance <= allowed_radius:
        geo_trust_score = 100 if geo_distance <= 15 else (70 if geo_distance <= 25 else 40)
        geo_verdict = "strong" if geo_distance <= 15 else ("moderate" if geo_distance <= 25 else "weak")
        reason = "Pass: Student is inside the classroom zone."
    else:
        geo_trust_score = 10
        geo_verdict = "reject"
        reason = f"Fail: Server Lock! Student is {geo_distance}m away."

    # 3. GPS Accuracy Penalty (Anti-Spoofing)
    acc = float(student_accuracy)
    if acc > 30:
        penalty = min((acc - 30) * 0.5, 40)
        geo_trust_score = max(int(geo_trust_score - penalty), 5)
        print(f"⚠️ Warning: Poor GPS signal detected. Applying penalty.")

    # 4. Terminal Output
    print(f"Calculated Distance: {geo_distance} meters")
    print(f"Trust Score:         {geo_trust_score}/100")
    print(f"Verdict:             {geo_verdict.upper()}")
    print(f"Result:              {reason}")
    print("-" * 25)

# ==========================================
# TEST SCENARIOS
# ==========================================

TEACHER_LAT = 28.6139
TEACHER_LNG = 77.2090

# Scenario 1: Perfect Check-in
test_attendance_geo(TEACHER_LAT, TEACHER_LNG, 28.61393, 77.2090, student_accuracy=5)

# Scenario 2: Back of the Classroom
test_attendance_geo(TEACHER_LAT, TEACHER_LNG, 28.61415, 77.2090, student_accuracy=10)

# Scenario 3: Outside the building
test_attendance_geo(TEACHER_LAT, TEACHER_LNG, 28.6148, 77.2090, student_accuracy=10)

# Scenario 4: Poor GPS accuracy
test_attendance_geo(TEACHER_LAT, TEACHER_LNG, 28.61393, 77.2090, student_accuracy=60)