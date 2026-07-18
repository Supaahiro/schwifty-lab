<script setup lang="ts">
import { RECORD_TYPES, type RRSet } from "../api/types";

defineProps<{ rrsets: RRSet[] }>();

const emit = defineEmits<{
  edit: [rrset: RRSet];
  remove: [rrset: RRSet];
}>();

function isManaged(rrset: RRSet): boolean {
  // SOA (and anything else outside the UI's type whitelist) stays read-only.
  return (RECORD_TYPES as readonly string[]).includes(rrset.type);
}
</script>

<template>
  <table>
    <thead>
      <tr>
        <th>Name</th>
        <th>Type</th>
        <th>TTL</th>
        <th>Content</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="rrset in rrsets" :key="`${rrset.name}/${rrset.type}`">
        <td class="mono">{{ rrset.name }}</td>
        <td><span class="tag">{{ rrset.type }}</span></td>
        <td>{{ rrset.ttl }}</td>
        <td class="mono">
          <div v-for="record in rrset.records" :key="record.content">
            {{ record.content }}
            <span v-if="record.disabled" class="muted">(disabled)</span>
          </div>
        </td>
        <td class="actions">
          <template v-if="isManaged(rrset)">
            <button @click="emit('edit', rrset)">Edit</button>
            <button class="danger" @click="emit('remove', rrset)">Delete</button>
          </template>
        </td>
      </tr>
    </tbody>
  </table>
</template>
