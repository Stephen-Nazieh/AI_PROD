## Lesson 1: Squeeze Theorem
{'type': 'text', 'text': '```json
{
  "name": "write",
  "arguments": {
    "path": "lessons/squeeze_theorem.md",
    "content": "# Squeeze Theorem\
\
## Overview\
The Squeeze Theorem, also known as the Sandwich Theorem or the Pinching Theorem, is a fundamental concept in calculus used to find the limit of a function when direct methods are difficult or impossible. It states that if a function \\( g(x) \\) is trapped between two functions \\( f(x) \\) and \\( h(x) \\) for all \\( x \\) in some interval around a point \\( c \\), and if the limits of \\( f(x) \\) and \\( h(x) \\) as \\( x \\) approaches \\( c \\) are equal, then the limit of \\( g(x) \\) as \\( x \\) approaches \\( c \\) must also be equal to that limit.\
\
## Theorem Statement\
Let \\( f(x) \\\\leq g(x) \\\\leq h(x) \\\\) for all \\( x \\\\) in some interval around \\( c \\\\) (except possibly at \\( c \\\\)). If\
\
\\\\[
\\\\lim_{{x \\\\to c}} f(x) = L \\\\quad \\\\text{and} \\\\quad \\\\lim_{{x \\\\to c}} h(x) = L,\
\\\\]\
\
then\
\
\\\\[
\\\\lim_{{x \\\\to c}} g(x) = L.\
\\\\]\
\
## Example\
Consider the function \\( g(x) = x^2 \\\\sin(1/x) \\\\). We want to find \\( \\\\lim_{{x \\\\to 0}} g(x) \\\\).\
\
First, note that \\( -1 \\\\leq \\\\sin(1/x) \\\\leq 1 \\\\) for all \\( x \\\
eq 0 \\\\). Therefore,\
\
\\\\[
-x^2 \\\\leq x^2 \\\\sin(1/x) \\\\leq x^2.\
\\\\]\
\
As \\( x \\\\to 0 \\\\), both \\( -x^2 \\\\) and \\( x^2 \\\\) approach 0. By the Squeeze Theorem,\
\
\\\\[
\\\\lim_{{x \\\\to 0}} x^2 \\\\sin(1/x) = 0.\
\\\\]\
\
## Conclusion\
The Squeeze Theorem is a powerful tool for evaluating limits that are difficult to compute directly. By finding functions that bound the given function and have the same limit, we can conclude that the limit of the given function must also be that value."
  }
}
```<|im_end|>
```json
{
  "name": "write",
  "arguments": {
    "path": "lessons/squeeze_theorem.md",
    "content": "# Squeeze Theorem\
\
## Overview\
The Squeeze Theorem, also known as the Sandwich Theorem or the Pinching Theorem, is a fundamental concept in calculus used to find the limit of a function when direct methods are difficult or impossible. It states that if a function \\( g(x) \\) is trapped between two functions \\( f(x) \\) and \\( h(x) \\) for all \\( x \\) in some interval around a point \\( c \\), and if the limits of \\( f(x) \\) and \\( h(x) \\) as \\( x \\) approaches \\( c \\) are equal, then the limit of \\( g(x) \\) as \\( x \\) approaches \\( c \\) must also be equal to that limit.\
\
## Theorem Statement\
Let \\( f(x) \\\\leq g(x) \\\\leq h(x) \\\\) for all \\( x \\\\) in some interval around \\( c \\\\) (except possibly at \\( c \\\\)). If\
\
\\\\[
\\\\lim_{{x \\\\to c}} f(x) = L \\\\quad \\\\text{and} \\\\quad \\\\lim_{{x \\\\to c}} h(x) = L,\
\\\\]\
\
then\
\
\\\\[
\\\\lim_{{x \\\\to c}} g(x) = L.\
\\\\]\
\
## Example\
Consider the function \\( g(x) = x^2 \\\\sin(1/x) \\\\). We want to find \\( \\\\lim_{{x \\\\to 0}} g(x) \\\\).\
\
First, note that \\( -1 \\\\leq \\\\sin(1/x) \\\\leq 1 \\\\) for all \\( x \\\
eq 0 \\\\). Therefore,\
\
\\\\[
-x^2 \\\\leq x^2 \\\\sin(1/x) \\\\leq x^2.\
\\\\]\
\
As \\( x \\\\to 0 \\\\), both \\( -x^2 \\\\) and \\( x^2 \\\\) approach 0. By the Squeeze Theorem,\
\
\\\\[
\\\\lim_{{x \\\\to 0}} x^2 \\\\sin(1/x) = 0.\
\\\\]\
\
## Conclusion\
The Squeeze Theorem is a powerful tool for evaluating limits that are difficult to compute directly. By finding functions that bound the given function and have the same limit, we can conclude that the limit of the given function must also be that value."
  }
}
```<|im_end|>
'}