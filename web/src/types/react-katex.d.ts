declare module 'react-katex' {
  import { Component } from 'react';
  
  interface KatexProps {
    children?: string;
    math?: string;
    errorColor?: string;
    renderError?: (error: Error) => JSX.Element;
  }
  
  export class InlineMath extends Component<KatexProps> {}
  export class BlockMath extends Component<KatexProps> {}
}
