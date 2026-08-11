import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from "@mui/material";
import { useTranslation } from "react-i18next";

const ConfirmDialog = ({
  open,
  title,
  onClose,
  onConfirm,
  confirmText,
  confirmColor = "primary",
  children,
}) => {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText>{children}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("common.actions.cancel")}</Button>
        <Button variant="contained" color={confirmColor} onClick={onConfirm}>
          {confirmText ?? t("common.actions.confirm")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ConfirmDialog;
