import { useState } from 'react'
import { EasyMode } from '@/features/easy/EasyMode'
import { HardStub } from '@/features/hard/HardStub'
import { HomeScreen } from '@/features/home/HomeScreen'

export type Screen = 'home' | 'easy' | 'hard'

export default function App() {
  const [screen, setScreen] = useState<Screen>('home')

  if (screen === 'easy') {
    return <EasyMode onBack={() => setScreen('home')} />
  }

  if (screen === 'hard') {
    return <HardStub onBack={() => setScreen('home')} />
  }

  return <HomeScreen onEasy={() => setScreen('easy')} />
}
