// 03-filtering/debounce-time.ts
// Emits values after a specified delay
//
// pnpm exec ts-node 03-filtering\debounce-time.ts

import { debounceTime, from } from "rxjs";

from([1, 2, 3]).pipe(debounceTime(300)).subscribe(console.log)