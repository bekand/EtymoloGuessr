import { Navigate, Route, Routes } from 'react-router-dom'
import { EasyMode } from '@/features/easy/EasyMode'
import { HardMode } from '@/features/hard/HardMode'
import { MediumMode } from '@/features/medium/MediumMode'
import { HomeScreen } from '@/features/home/HomeScreen'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeScreen />} />
      <Route path="/easy" element={<EasyMode />} />
      <Route path="/medium" element={<MediumMode />} />
      <Route path="/hard" element={<HardMode />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
