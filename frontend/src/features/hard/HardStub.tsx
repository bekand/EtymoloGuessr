import { Colophon, InkButton, Sheet } from '@/ui'
import styles from './HardStub.module.css'

type HardStubProps = {
  onBack: () => void
}

export function HardStub({ onBack }: HardStubProps) {
  return (
    <Sheet as="main" tone="kraft" className={styles.stub}>
      <header className={styles.header}>
        <InkButton variant="ghost" onClick={onBack}>
          ← Home
        </InkButton>
        <p className={styles.brand}>EtymoGuessr</p>
      </header>
      <div className={styles.body}>
        <h1 className={styles.title}>Hard mode</h1>
        <p className={styles.copy}>Coming soon — place ancestors and draw ink edges once the API lands.</p>
      </div>
      <Colophon />
    </Sheet>
  )
}
