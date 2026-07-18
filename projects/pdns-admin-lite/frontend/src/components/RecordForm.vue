<script setup lang="ts">
import { computed, ref } from "vue";

import { RECORD_TYPES, type RecordInput, type RecordType, type RRSet } from "../api/types";

const props = defineProps<{
  zoneName: string;
  initial: RRSet | null;
  busy: boolean;
}>();

const emit = defineEmits<{
  save: [input: RecordInput];
  cancel: [];
}>();

// Editing replaces an existing rrset, so name and type stay fixed:
// they are the rrset's identity.
const isEdit = props.initial !== null;

const name = ref(props.initial?.name ?? "");
const type = ref<RecordType>((props.initial?.type as RecordType) ?? "A");
const ttl = ref(props.initial?.ttl ?? 3600);
const contents = ref(props.initial?.records.map((record) => record.content).join("\n") ?? "");

const records = computed(() =>
  contents.value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0),
);

const valid = computed(() => name.value.trim().length > 0 && ttl.value >= 1 && records.value.length > 0);

function submit(): void {
  if (!valid.value) {
    return;
  }
  emit("save", {
    name: name.value.trim(),
    type: type.value,
    ttl: ttl.value,
    records: records.value,
  });
}
</script>

<template>
  <form class="record-form" @submit.prevent="submit">
    <h2>{{ isEdit ? "Edit record set" : "Add record" }}</h2>
    <div class="fields">
      <label>
        Name
        <input
          v-model="name"
          :disabled="isEdit"
          :placeholder="`e.g. web (relative to ${props.zoneName})`"
        />
      </label>
      <label>
        Type
        <select v-model="type" :disabled="isEdit">
          <option v-for="recordType in RECORD_TYPES" :key="recordType" :value="recordType">
            {{ recordType }}
          </option>
        </select>
      </label>
      <label>
        TTL (s)
        <input v-model.number="ttl" type="number" min="1" />
      </label>
    </div>
    <label>
      Content (one value per line)
      <textarea v-model="contents" rows="3" placeholder="192.168.0.10"></textarea>
    </label>
    <div class="form-actions">
      <button type="submit" :disabled="!valid || props.busy">
        {{ props.busy ? "Saving…" : "Save" }}
      </button>
      <button type="button" class="secondary" @click="emit('cancel')">Cancel</button>
    </div>
  </form>
</template>
