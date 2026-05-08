import { useRef, useEffect, useState } from 'react'

export function Sparkline({ data, color, height = 32 }: { data: number[]; color: string; height?: number }) {
  const [animate, setAnimate] = useState(false)
  const prevDataLen = useRef(0)

  useEffect(() => {
    if (data.length >= 2 && prevDataLen.current !== data.length) {
      setAnimate(false)
      requestAnimationFrame(() => setAnimate(true))
      prevDataLen.current = data.length
    }
  }, [data])

  if (data.length < 2) return null;
  const max = Math.max(...data, 0.001);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const w = 100;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  }).join(' ');

  const pathLength = data.reduce((acc, _, i) => {
    if (i === 0) return 0;
    const x1 = ((i - 1) / (data.length - 1)) * w;
    const y1 = height - ((data[i - 1] - min) / range) * (height - 4) - 2;
    const x2 = (i / (data.length - 1)) * w;
    const y2 = height - ((data[i] - min) / range) * (height - 4) - 2;
    return acc + Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
  }, 0);

  return (
    <svg viewBox={`0 0 ${w} ${height}`} style={{ width: '100%', height, display: 'block' }} preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={pathLength}
        strokeDashoffset={animate ? 0 : pathLength}
        style={{ transition: 'stroke-dashoffset 0.8s ease-out' }}
      />
    </svg>
  );
}
