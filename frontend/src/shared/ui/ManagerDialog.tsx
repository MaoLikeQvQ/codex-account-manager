import { Dialog, type DialogProps } from "@mui/material";

/** Keep drafts and confirmations open when a background click lands on the overlay. */
export default function ManagerDialog({ onClose, ...props }: DialogProps) {
  return (
    <Dialog
      {...props}
      onClose={(event, reason) => {
        if (reason !== "backdropClick") onClose?.(event, reason);
      }}
    />
  );
}
