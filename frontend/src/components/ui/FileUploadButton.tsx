import type { ChangeEvent, Ref } from "react";

export interface FileUploadButtonProps {
  label: string;
  busyLabel: string;
  busy: boolean;
  accept: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
  inputRef?: Ref<HTMLInputElement>;
}

/**
 * Button-styled file input (native `<input type="file">` hidden behind a
 * label so it inherits the same `.btn` look/transitions as every other
 * button in the app).
 */
export default function FileUploadButton({
  label,
  busyLabel,
  busy,
  accept,
  onChange,
  inputRef,
}: FileUploadButtonProps) {
  return (
    <label className="btn btn-primary">
      {busy ? busyLabel : label}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={onChange}
        disabled={busy}
        className="file-input-hidden"
      />
    </label>
  );
}
