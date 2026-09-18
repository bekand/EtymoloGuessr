import type { MediumPrompt, PuzzlePrompt, SolveResponse } from '@/api/types'

export const easyPrompt: PuzzlePrompt = {
  id: 'p0easy000000000000',
  mode: 'easy',
  langPair: 'de-en',
  leafA: { lang: 'English', term: 'father', gloss: 'male parent' },
  leafB: { lang: 'German', term: 'Vater', gloss: 'father' },
  choices: [
    { id: 'c0', gloss: 'a male parent' },
    { id: 'c1', gloss: 'a river' },
    { id: 'c2', gloss: 'to walk' },
    { id: 'c3', gloss: 'a stone' },
  ],
}

export const nextEasyPrompt: PuzzlePrompt = {
  ...easyPrompt,
  id: 'p1easy000000000000',
  leafA: { lang: 'English', term: 'hound', gloss: 'a hunting dog' },
  leafB: { lang: 'German', term: 'Hund', gloss: 'a domestic animal' },
}

export const hardPrompt: PuzzlePrompt = {
  id: 'p0hard000000000000',
  mode: 'hard',
  langPair: 'de-en',
  leafA: easyPrompt.leafA,
  leafB: easyPrompt.leafB,
  choices: easyPrompt.choices,
  promptGraph: {
    nodes: [
      { id: 'English:father', lang: 'English', term: 'father', gloss: 'male parent', role: 'leaf' },
      { id: 'German:Vater', lang: 'German', term: 'Vater', gloss: 'father', role: 'leaf' },
      { id: 'Proto-Germanic:*fader', lang: 'Proto-Germanic', term: '*fader', gloss: 'a male parent', role: 'ancestor' },
      { id: 'Proto-Indo-European:*ph2ter', lang: 'Proto-Indo-European', term: '*ph₂tḗr', gloss: 'father', role: 'ancestor' },
    ],
    edges: [],
  },
}

export const easySolve: SolveResponse = {
  correct: true,
  correctChoice: 'c0',
  choices: easyPrompt.choices,
  goldGraph: {
    nodes: [
      { id: 'English:father', lang: 'English', term: 'father', role: 'leaf' },
      { id: 'German:Vater', lang: 'German', term: 'Vater', role: 'leaf' },
      {
        id: 'Proto-Germanic:*fader',
        lang: 'Proto-Germanic',
        term: '*fader',
        gloss: 'a male parent',
        role: 'ancestor',
      },
    ],
    edges: [
      { from: 'English:father', to: 'Proto-Germanic:*fader' },
      { from: 'German:Vater', to: 'Proto-Germanic:*fader' },
    ],
  },
}

export const mediumPrompt: MediumPrompt = {
  id: 'm11111111111111111,m22222222222222222,m33333333333333333,m44444444444444444',
  mode: 'medium',
  leaves: [
    { id: 'tok01', lang: 'English', term: 'father' },
    { id: 'tok02', lang: 'German', term: 'Vater' },
    { id: 'tok03', lang: 'English', term: 'hound' },
    { id: 'tok04', lang: 'German', term: 'Hund' },
    { id: 'tok05', lang: 'English', term: 'gift' },
    { id: 'tok06', lang: 'German', term: 'Gift' },
    { id: 'tok07', lang: 'English', term: 'house' },
    { id: 'tok08', lang: 'German', term: 'Haus' },
  ],
}

export const nextMediumPrompt: MediumPrompt = {
  ...mediumPrompt,
  id: 'n11111111111111111,n22222222222222222,n33333333333333333,n44444444444444444',
  leaves: mediumPrompt.leaves.map((leaf, i) => ({
    ...leaf,
    id: `next${i}`,
    term: `${leaf.term}-next`,
  })),
}

export const mediumSolve: SolveResponse = {
  correct: true,
  ancestors: [
    { lang: 'Proto-Germanic', term: '*fader', gloss: 'a male parent' },
    { lang: 'Proto-Germanic', term: '*hundaz', gloss: 'a dog' },
    { lang: 'Proto-Germanic', term: '*giftiz', gloss: 'something given' },
    { lang: 'Proto-Germanic', term: '*hūsą', gloss: 'a dwelling' },
  ],
  pairOrigins: [
    {
      pair: [mediumPrompt.leaves[0], mediumPrompt.leaves[1]],
      ancestor: { lang: 'Proto-Germanic', term: '*fader', gloss: 'a male parent' },
    },
    {
      pair: [mediumPrompt.leaves[2], mediumPrompt.leaves[3]],
      ancestor: { lang: 'Proto-Germanic', term: '*hundaz', gloss: 'a dog' },
    },
    {
      pair: [mediumPrompt.leaves[4], mediumPrompt.leaves[5]],
      ancestor: { lang: 'Proto-Germanic', term: '*giftiz', gloss: 'something given' },
    },
    {
      pair: [mediumPrompt.leaves[6], mediumPrompt.leaves[7]],
      ancestor: { lang: 'Proto-Germanic', term: '*hūsą', gloss: 'a dwelling' },
    },
  ],
}
