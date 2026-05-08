import { useEffect, useRef, useState } from 'react'

export function useCountUp(target: number, duration = 600): number {
  const [current, setCurrent] = useState(0)
  const rafRef = useRef<number | null>(null)
  const startRef = useRef<number | null>(null)
  const fromRef = useRef(0)

  useEffect(() => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)

    fromRef.current = current
    startRef.current = null

    if (target === 0) {
      setCurrent(0)
      return
    }

    const animate = (timestamp: number) => {
      if (startRef.current == null) startRef.current = timestamp
      const elapsed = timestamp - startRef.current
      const progress = Math.min(elapsed / duration, 1)
      // ease-out cubic
      const eased = 1 - (1 - progress) ** 3
      setCurrent(fromRef.current + (target - fromRef.current) * eased)

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      }
    }

    rafRef.current = requestAnimationFrame(animate)
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [target, duration])

  return current
}
