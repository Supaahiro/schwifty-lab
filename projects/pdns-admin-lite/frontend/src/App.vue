<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
</script>

<template>
  <header class="topbar">
    <RouterLink to="/" class="brand">pdns-admin-lite</RouterLink>
    <span class="tagline">PowerDNS record manager</span>
  </header>
  <main class="container">
    <RouterView />
  </main>
</template>
