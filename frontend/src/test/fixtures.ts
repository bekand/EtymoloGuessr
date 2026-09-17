import type { PuzzlePrompt, SolveResponse } from '@/api/types'

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
