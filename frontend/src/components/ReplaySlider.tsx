interface Props {
  stepCount: number;
  currentStep: number;
  onStepChange: (step: number) => void;
}

export function ReplaySlider({ stepCount, currentStep, onStepChange }: Props) {
  if (stepCount === 0) return null;

  return (
    <div className="flex items-center gap-3 border-b border-surface-3 bg-surface-1 px-4 py-2">
      {/* Back button */}
      <button
        onClick={() => onStepChange(Math.max(0, currentStep - 1))}
        disabled={currentStep === 0}
        className="rounded p-1 text-gray-400 transition-colors hover:bg-surface-3 hover:text-white disabled:opacity-30"
        title="Previous step (Left arrow / k)"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M10.3 12.3a1 1 0 0 1-1.4 0l-3.6-3.6a1 1 0 0 1 0-1.4l3.6-3.6a1 1 0 1 1 1.4 1.4L7.4 8l2.9 2.9a1 1 0 0 1 0 1.4z" />
        </svg>
      </button>

      {/* Slider */}
      <input
        type="range"
        min={0}
        max={stepCount - 1}
        value={currentStep}
        onChange={(e) => onStepChange(parseInt(e.target.value, 10))}
        className="flex-1 cursor-pointer accent-accent-blue"
      />

      {/* Forward button */}
      <button
        onClick={() => onStepChange(Math.min(stepCount - 1, currentStep + 1))}
        disabled={currentStep === stepCount - 1}
        className="rounded p-1 text-gray-400 transition-colors hover:bg-surface-3 hover:text-white disabled:opacity-30"
        title="Next step (Right arrow / j)"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M5.7 3.7a1 1 0 0 1 1.4 0l3.6 3.6a1 1 0 0 1 0 1.4l-3.6 3.6a1 1 0 0 1-1.4-1.4L8.6 8 5.7 5.1a1 1 0 0 1 0-1.4z" />
        </svg>
      </button>

      {/* Step counter */}
      <span className="w-16 text-center font-mono text-xs text-gray-500">
        {currentStep + 1} / {stepCount}
      </span>
    </div>
  );
}
