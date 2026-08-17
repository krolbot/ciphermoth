import { action, thunk } from "easy-peasy";

import apiClient from "../api/client";
import { errorDetail } from "../lib/http";
import i18n from "../i18n";

const Users = {
  users: [],
  setUsers: action((state, users) => {
    state.users = users;
  }),
  addUser: action((state, user) => {
    state.users.push(user);
  }),
  get: thunk(async (actions) => {
    try {
      const { data } = await apiClient.get("/users");
      actions.setUsers(data);
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.loadUsers")));
    }
  }),
  create: thunk(async (actions, payload) => {
    try {
      const { data } = await apiClient.post("/users", payload);
      const user = { ...data };
      delete user.service_token;
      actions.addUser(user);
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.createUser")));
    }
  }),
  update: thunk(async (actions, { userId, ...payload }) => {
    try {
      await apiClient.patch(`/users/${userId}`, payload);
      await actions.get();
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.updateUser")));
    }
  }),
  shareTargets: thunk(async () => {
    try {
      const { data } = await apiClient.get("/users/share-targets");
      return data;
    } catch (err) {
      throw new Error(await errorDetail(err, i18n.t("errors.loadShareTargets")));
    }
  }),
};

export default Users;
