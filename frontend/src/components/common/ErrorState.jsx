import { Button } from "../ui/Button.jsx";

export function ErrorState({ message, onRetry }) {
  return (
    <div className="rounded-lg border border-danger/30 bg-danger/10 p-5 text-sm text-danger" role="alert">
      <p className="font-semibold">Unable to load this section.</p>
      <p className="mt-1">{message}</p>
      {onRetry ? (
        <Button className="mt-4" variant="secondary" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
