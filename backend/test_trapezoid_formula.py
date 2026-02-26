"""
Test the trapezoid formula to identify the bug
"""

# Current trapezoid boundaries from diagnostic
x_right_bot = 71.49
x_right_top = 73.76
y_bot = 26.01
y_top = 39.02

print("="*80)
print("TRAPEZOID RIGHT EDGE FORMULA TEST")
print("="*80)
print(f"\nEdge goes from:")
print(f"  Bottom point: ({x_right_bot}, {y_bot})")
print(f"  Top point:    ({x_right_top}, {y_top})")
print()

# Test at x = x_right_bot (should give y_bot)
print("="*80)
print("CURRENT FORMULA (BUGGY)")
print("="*80)

slope_current = (y_bot - y_top) / (x_right_top - x_right_bot)
print(f"slope = (y_bot - y_top) / (x_right_top - x_right_bot)")
print(f"      = ({y_bot} - {y_top}) / ({x_right_top} - {x_right_bot})")
print(f"      = {slope_current:.4f}")
print()

test_x_values = [71.49, 71.50, 72.00, 73.00, 73.76]

for x in test_x_values:
    y_min_current = y_top + slope_current * (x - x_right_bot)
    print(f"At x={x:.2f}:  y_min = y_top + slope * (x - x_right_bot)")
    print(f"           y_min = {y_top} + {slope_current:.4f} * ({x} - {x_right_bot})")
    print(f"           y_min = {y_min_current:.2f}")
    
    if x == x_right_bot:
        print(f"           ❌ Should be {y_bot} at x_right_bot!")
    elif x == x_right_top:
        print(f"           ❓ Should be {y_top} at x_right_top?")
    print()

print("="*80)
print("CORRECT FORMULA (FIXED)")
print("="*80)

slope_correct = (y_top - y_bot) / (x_right_top - x_right_bot)
print(f"slope = (y_top - y_bot) / (x_right_top - x_right_bot)")
print(f"      = ({y_top} - {y_bot}) / ({x_right_top} - {x_right_bot})")
print(f"      = {slope_correct:.4f}")
print()

for x in test_x_values:
    y_min_correct = y_bot + slope_correct * (x - x_right_bot)
    print(f"At x={x:.2f}:  y_min = y_bot + slope * (x - x_right_bot)")
    print(f"           y_min = {y_bot} + {slope_correct:.4f} * ({x} - {x_right_bot})")
    print(f"           y_min = {y_min_correct:.2f}")
    
    if x == x_right_bot:
        print(f"           ✅ Correct! Gives y_bot at x_right_bot")
    elif x == x_right_top:
        print(f"           ✅ Correct! Gives y_top at x_right_top")
    print()

print("="*80)
print("COMPARISON FOR LOUISVILLE (x=71.50, y=28.75)")
print("="*80)
x_louisville = 71.50
y_louisville = 28.75

y_min_current = y_top + slope_current * (x_louisville - x_right_bot)
y_min_correct = y_bot + slope_correct * (x_louisville - x_right_bot)

print(f"\nCurrent (buggy) formula:")
print(f"  Bottom boundary at x={x_louisville}: {y_min_current:.2f}")
print(f"  Louisville's y={y_louisville}")
print(f"  Inside? {y_louisville >= y_min_current}")
print()

print(f"Correct formula:")
print(f"  Bottom boundary at x={x_louisville}: {y_min_correct:.2f}")
print(f"  Louisville's y={y_louisville}")
print(f"  Inside? {y_louisville >= y_min_correct}")
print()

if y_louisville >= y_min_correct:
    print(f"✅ With the CORRECT formula, Louisville WOULD be inside!")
else:
    print(f"❌ Even with the correct formula, Louisville is still outside")

print("="*80)
