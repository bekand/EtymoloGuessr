import { useCallback, useEffect, useState, type AnimationEvent } from 'react'

const SETTLE_FALLBACK_MS = 400

export function useSettlingClip() {
  const [settling, setSettling] = useState(true)

  const onAnimationEnd = useCallback((event: AnimationEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget) {
      return
    }
    setSettling(false)
  }, [])

  useEffect(() => {
    if (!settling) {
      return
    }
    const id = window.setTimeout(() => setSettling(false), SETTLE_FALLBACK_MS)
    return () => window.clearTimeout(id)
  }, [settling])

  return { settling, onAnimationEnd }
}
