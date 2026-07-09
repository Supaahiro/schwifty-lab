// 03-filtering/distinct-until-changed.ts
// Emits values only when they are distinct from the previous value
//
// pnpm exec ts-node 03-filtering\distinct-until-changed.ts

import { distinctUntilChanged, from } from "rxjs";

from([1, 1, 2, 2, 3]).pipe(distinctUntilChanged()).subscribe(console.log)