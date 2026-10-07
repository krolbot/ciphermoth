export const userAdminActions = (user, currentUserId) => {
  const isSelf = user.id === currentUserId;
  const isHuman = user.role !== "service";
  return {
    canDelete: !isSelf,
    canRequirePasswordChange: !isSelf && isHuman,
    canRevokeSessions: !isSelf && isHuman,
  };
};
