// Never let a wall-clock correction count as elapsed endurance time.
export function elapsed(startedMono,nowMono,durationMs){
  return {monotonicElapsedMs:Math.max(0,nowMono-startedMono),complete:nowMono-startedMono>=durationMs};
}
export function observation(previousWall,previousMono,nowWall,nowMono){
  const wallGapMs=nowWall-previousWall,monotonicGapMs=nowMono-previousMono,clockDifferenceMs=wallGapMs-monotonicGapMs;
  return {wallGapMs,monotonicGapMs:Math.round(monotonicGapMs),clockDifferenceMs:Math.round(clockDifferenceMs),
    hostGap:wallGapMs>45000||monotonicGapMs>45000,clockDiscontinuity:Math.abs(clockDifferenceMs)>5000};
}
