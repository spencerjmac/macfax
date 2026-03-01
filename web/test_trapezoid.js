// Quick test to debug Louisville trapezoid check
const trapezoid = {
  x_left_top: 65.1007,
  x_right_top: 73.6844,
  x_left_bot: 67.5781,
  x_right_bot: 71.059,
  y_top: 38.8205,
  y_bot: 26.267681999999997
};

const louisville = {
  tempo: 71.61,
  em: 28.21,
  name: 'Louisville'
};

function checkInside(x, y, trap) {
  console.log(`\nChecking ${louisville.name}:`);
  console.log(`  Tempo: ${x}, EM: ${y}`);
  
  // X bounds check
  if (x < trap.x_left_top || x > trap.x_right_top) {
    console.log(`  ❌ Outside X bounds: ${trap.x_left_top} to ${trap.x_right_top}`);
    return false;
  }
  console.log(`  ✓ Within X bounds`);
  
  // Y top check
  if (y > trap.y_top) {
    console.log(`  ❌ Above y_top: ${trap.y_top}`);
    return false;
  }
  console.log(`  ✓ Below y_top`);
  
  // Calculate y_min at this x position
  let y_min;
  if (x <= trap.x_left_bot) {
    const slope = (trap.y_bot - trap.y_top) / (trap.x_left_bot - trap.x_left_top);
    y_min = trap.y_top + slope * (x - trap.x_left_top);
    console.log(`  Left slant region: y_min = ${y_min}`);
  } else if (x < trap.x_right_bot) {
    y_min = trap.y_bot;
    console.log(`  Flat bottom region: y_min = ${y_min}`);
  } else {
    const slope = (trap.y_top - trap.y_bot) / (trap.x_right_top - trap.x_right_bot);
    y_min = trap.y_bot + slope * (x - trap.x_right_bot);
    console.log(`  Right slant region: y_min = ${y_min}`);
  }
  
  const inside = y >= y_min;
  console.log(`  ${inside ? '✓' : '❌'} ${y} >= ${y_min} = ${inside}`);
  
  return inside;
}

const result = checkInside(louisville.tempo, louisville.em, trapezoid);
console.log(`\nFinal result: ${result ? 'INSIDE' : 'OUTSIDE'}`);
