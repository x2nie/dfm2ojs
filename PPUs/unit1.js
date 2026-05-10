// import {TSet} from '@runtime';
console.log('Initializing unit1...');

// Uses (4):
import {TPersistent} from './classes.js'
import { symbols, set_of, property } from '@runtime';
//   - System
//   - objpas
//   - Classes
//   - sysutils

// Declared Types, excluding classes and $vmt (2):
export const TFooMode = symbols('fmSmall', 'fmMedium', 'fmLarge');
export const TFooOptions = set_of(TFooMode);

// Classes with published properties (2):
export class TFoo extends TPersistent {
      Count = property(Number, 7)
      Enabled = property(Boolean, true)
      Mode = property(TFooMode, 'fmMedium')
      Name = property(String, '')
      Options = property(TFooOptions)
}
export class TBar extends TFoo {
      Level = property(Number, 3)
      Title = property(String, '')
      Visible = property(Boolean, false)
}
