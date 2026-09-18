type StampHintLabels = {
	onError: string
	onReady: string
	onSubmitError: string
	onSubmitReady: string
}

type StampHintState = {
	loadError: unknown
	submitError: unknown
	ready: boolean
}

export function getStampHint(
	state: StampHintState,
	labels: StampHintLabels,
): string {
	if (state.loadError) {
		return state.loadError instanceof Error ? state.loadError.message : labels.onError
	}
	if (state.submitError) {
		return state.submitError instanceof Error
			? state.submitError.message
			: labels.onSubmitError
	}
	return state.ready ? labels.onSubmitReady : labels.onReady
}