import { Colophon, InkButton, Sheet } from '@/ui'
import './HardStub.scss'

type HardStubProps = {
  onBack: () => void
}

export function HardStub({ onBack }: HardStubProps) {
  return (
    <Sheet as="main" tone="kraft" className="hardStub">
      <header className="header">
        <InkButton variant="ghost" onClick={onBack}>
          ← Home
        </InkButton>
        <p className="brand">EtymoGuessr</p>
      </header>
      <div className="body">
        <h1 className="title">Hard mode</h1>
        <p className="copy">Coming soon — place ancestors and draw ink edges once the API lands.</p>
      </div>
      <Colophon />
    </Sheet>
  )
}
