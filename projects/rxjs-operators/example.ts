import { interval, of } from 'rxjs';
import { map, switchMap, take } from 'rxjs/operators';

interval(1000).pipe(
  take(3),
  switchMap(i => of(`Stream ${i}`).pipe(map(v => `${v} ✅`)))
).subscribe(console.log);