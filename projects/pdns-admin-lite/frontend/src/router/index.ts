import { createRouter, createWebHistory } from "vue-router";

export default createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "zones",
      component: () => import("../views/ZonesView.vue"),
    },
    {
      path: "/zones/:zoneId",
      name: "zone-detail",
      component: () => import("../views/ZoneDetailView.vue"),
      props: true,
    },
  ],
});
