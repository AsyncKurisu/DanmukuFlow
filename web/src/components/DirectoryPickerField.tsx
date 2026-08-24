import { useState } from "react";
import { ApiError, selectDirectory } from "../api/client";

interface DirectoryPickerFieldProps {
  label: string;
  value: string;
  placeholder: string;
  kind: "output" | "video";
  onChange: (value: string) => void;
  onError: (message: string) => void;
}

export function DirectoryPickerField({
  label,
  value,
  placeholder,
  kind,
  onChange,
  onError,
}: DirectoryPickerFieldProps) {
  const [busy, setBusy] = useState(false);

  async function handlePick() {
    setBusy(true);
    onError("");
    try {
      const selected = await selectDirectory(kind);
      if (selected) {
        onChange(selected);
      }
    } catch (error) {
      onError(error instanceof ApiError ? error.reason ?? error.detail : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="directory-picker">
      <input value={value} placeholder={placeholder} readOnly aria-label={label} />
      <button
        type="button"
        className="button secondary"
        disabled={busy}
        onClick={handlePick}
        aria-label={`浏览${label}`}
      >
        {busy ? "选择中..." : "浏览目录"}
      </button>
      {value && (
        <button
          type="button"
          className="button secondary"
          disabled={busy}
          onClick={() => onChange("")}
          aria-label={`清空${label}`}
          title={`清空${label}`}
        >
          清空
        </button>
      )}
    </div>
  );
}
