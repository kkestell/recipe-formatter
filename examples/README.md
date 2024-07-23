# Examples

## PDF Output

```
URL='https://www.allrecipes.com/recipe/17644/german-chocolate-cake-iii/'
```

| ![Example 1](example1-1.jpg) |
|:----------------------------:|
|  `rf -o example1.pdf $URL`   |

| ![Example 2](example2-1.jpg) |
|:----------------------------:|
| `rf -o example2.pdf -n $URL` |

|  ![Example 3](example3-1.jpg)   |
|:-------------------------------:|
| `rf -o example3.pdf -n -g $URL` |

|             ![Example 4](example4-1.jpg)             |
|:----------------------------------------------------:|
| `rf -o example4.pdf -n -g -r "sub goat's milk" $URL` |
