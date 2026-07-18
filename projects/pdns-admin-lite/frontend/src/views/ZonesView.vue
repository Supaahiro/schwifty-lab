<script setup lang="ts">
import { onMounted, ref } from "vue";

import { ApiError, getZones } from "../api/client";
import type { ZoneSummary } from "../api/types";

const zones = ref<ZoneSummary[]>([]);
const loading = ref(true);
const error = ref("");

onMounted(async () => {
  try {
    zones.value = await getZones();
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : String(err);
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <h1>Zones</h1>
  <p v-if="loading" class="muted">Loading zones…</p>
  <p v-else-if="error" class="error">{{ error }}</p>
  <p v-else-if="zones.length === 0" class="muted">No zones found.</p>
  <table v-else>
    <thead>
      <tr>
        <th>Name</th>
        <th>Kind</th>
        <th>Serial</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="zone in zones" :key="zone.id">
        <td>
          <RouterLink :to="{ name: 'zone-detail', params: { zoneId: zone.id } }">
            {{ zone.name }}
          </RouterLink>
        </td>
        <td>{{ zone.kind }}</td>
        <td>{{ zone.serial }}</td>
      </tr>
    </tbody>
  </table>
</template>
