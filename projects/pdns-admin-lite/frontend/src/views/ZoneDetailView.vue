<script setup lang="ts">
import { onMounted, ref } from "vue";

import { ApiError, createRecord, deleteRecord, getZone, updateRecord } from "../api/client";
import type { RecordInput, RRSet, ZoneDetail } from "../api/types";
import RecordForm from "../components/RecordForm.vue";
import RecordTable from "../components/RecordTable.vue";

const props = defineProps<{ zoneId: string }>();

const zone = ref<ZoneDetail | null>(null);
const loading = ref(true);
const error = ref("");
const showForm = ref(false);
const editing = ref<RRSet | null>(null);
const saving = ref(false);

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    zone.value = await getZone(props.zoneId);
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : String(err);
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function openAdd(): void {
  editing.value = null;
  showForm.value = true;
}

function openEdit(rrset: RRSet): void {
  editing.value = rrset;
  showForm.value = true;
}

function closeForm(): void {
  showForm.value = false;
  editing.value = null;
}

async function save(input: RecordInput): Promise<void> {
  saving.value = true;
  error.value = "";
  try {
    if (editing.value) {
      await updateRecord(props.zoneId, input);
    } else {
      await createRecord(props.zoneId, input);
    }
    closeForm();
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : String(err);
  } finally {
    saving.value = false;
  }
}

async function remove(rrset: RRSet): Promise<void> {
  if (!confirm(`Delete ${rrset.type} record set ${rrset.name}?`)) {
    return;
  }
  error.value = "";
  try {
    await deleteRecord(props.zoneId, rrset.name, rrset.type);
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : String(err);
  }
}
</script>

<template>
  <p><RouterLink to="/">← All zones</RouterLink></p>
  <p v-if="loading" class="muted">Loading zone…</p>
  <p v-else-if="error && !zone" class="error">{{ error }}</p>
  <template v-else-if="zone">
    <div class="zone-header">
      <h1>{{ zone.name }}</h1>
      <span class="muted">{{ zone.kind }} · serial {{ zone.serial }}</span>
      <button v-if="!showForm" @click="openAdd">Add record</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <RecordForm
      v-if="showForm"
      :zone-name="zone.name"
      :initial="editing"
      :busy="saving"
      @save="save"
      @cancel="closeForm"
    />
    <RecordTable :rrsets="zone.rrsets" @edit="openEdit" @remove="remove" />
  </template>
</template>
