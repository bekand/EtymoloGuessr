import type { AnimationEventHandler, ReactNode } from 'react'
import { Colophon, PlayHeader, Sheet } from '@/ui'
import { joinClasses } from '@/utils/joinClasses'

export type ModeShellProps = {
	mode: 'easy' | 'medium' | 'hard'
	streak: number
	settling: boolean
	onAnimationEnd: AnimationEventHandler<HTMLElement>
	children: ReactNode
}

export function ModeShell({
	mode,
	streak,
	settling,
	onAnimationEnd,
	children,
}: ModeShellProps) {
	return (
		<Sheet
			as="main"
			tone="kraft"
			className={joinClasses(`${mode}Mode`, settling && 'settling')}
			onAnimationEnd={onAnimationEnd}
		>
			<PlayHeader mode={mode} streak={streak} />
			{children}
			<Colophon />
		</Sheet>
	)
}