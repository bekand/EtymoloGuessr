function firstNumberInId(id: string): number {
  const digit = /\d/.exec(id)?.[0]
  return digit ? Number(digit) : 0
}

export function shuffle<T>(items: readonly T[], id: string): T[] {
  const next = [...items]
  const seed = firstNumberInId(id)
  for (let i = next.length - 1; i > 0; i -= 1) {
    const j = seed % (i + 1)
    const current = next[i]
    const swap = next[j]
    if (current !== undefined && swap !== undefined) {
      next[i] = swap
      next[j] = current
    }
  }
  return next
}
