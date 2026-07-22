import Button from "./Button";

export interface PaginationProps {
  page: number;
  totalPages: number;
  total: number;
  itemLabel?: string;
  onPrev: () => void;
  onNext: () => void;
}

/** Shared prev/next pager with a status label, used by any paginated list. */
export default function Pagination({
  page,
  totalPages,
  total,
  itemLabel = "items",
  onPrev,
  onNext,
}: PaginationProps) {
  if (totalPages <= 1) return null;

  return (
    <div className="pagination">
      <Button variant="secondary" disabled={page <= 1} onClick={onPrev}>
        Previous
      </Button>
      <span className="pagination-status">
        Page {page} of {totalPages} ({total} {itemLabel})
      </span>
      <Button variant="secondary" disabled={page >= totalPages} onClick={onNext}>
        Next
      </Button>
    </div>
  );
}
