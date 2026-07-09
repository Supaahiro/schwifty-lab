// 03-filtering/throttle-time.ts
// Emits values only when the specified time has passed without any new values
//
// pnpm exec ts-node 03-filtering\throttle-time.ts

import { interval, take, throttleTime } from "rxjs";

interval(100).pipe(throttleTime(300), take(5)).subscribe(console.log)