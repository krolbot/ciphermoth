import { useCallback } from "react";
import { useToaster } from "@gravity-ui/uikit";

let notificationId = 0;

const themes = {
  default: "normal",
  error: "danger",
  info: "info",
  success: "success",
  warning: "warning",
};

export const useSnackbar = () => {
  const { add, remove } = useToaster();

  const enqueueSnackbar = useCallback(
    (message, options = {}) => {
      const name = String(options.key ?? `cm-notification-${++notificationId}`);
      add({
        name,
        content: message,
        theme: themes[options.variant] ?? "normal",
        autoHiding: options.persist ? false : (options.autoHideDuration ?? 5000),
        isClosable: true,
      });
      return name;
    },
    [add]
  );

  const closeSnackbar = useCallback((name) => remove(String(name)), [remove]);

  return { enqueueSnackbar, closeSnackbar };
};
