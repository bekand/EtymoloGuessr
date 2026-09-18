import type { AnimationEventHandler, ReactNode } from 'react'
import { Colophon, PlayHeader, Sheet } from '@/ui'
import { joinClasses } from '@/utils/joinClasses'

export type ModeShellProps = {
	mode: 'easy' | 'medium' | 'hard'
	streak: number
	settling: boolean
	onAnimationEnd: AnimationEventHandler<HTMLElement>
	instruction?: ReactNode
	children: ReactNode
}

export function ModeShell({
	mode,
	streak,
	settling,
	onAnimationEnd,
	instruction,
	children,
}: ModeShellProps) {
	return (
		<Sheet
			as="main"
			tone="kraft"
			className={joinClasses('modeSheet', `${mode}Mode`, settling && 'settling')}
			header={<PlayHeader mode={mode} streak={streak} />}
			instruction={instruction}
			onAnimationEnd={onAnimationEnd}
		>
			{children}
			<Colophon />
		</Sheet>
	)
}