# Examples

## PDF Output

```
OPENAI_API_KEY='your-api-key'
URL='https://www.allrecipes.com/recipe/7399/tres-leches-milk-cake/'
```

| ![Example 1](example1-1.jpg) |
|:-------------------------------------:|
|       `rf -o example1.pdf $URL`       |

| ![Example 2](example2-1.jpg) |
|:-------------------------------------:|
|     `rf -o example2.pdf -n $URL`      |

| ![Example 3](example3-1.jpg) |
|:-------------------------------------:|
|    `rf -o example3.pdf -n -g $URL`    |

| ![Example 4](example4-1.jpg) ![Example 4](example4-2.jpg) |
|:---------------------------------------------------------------------------:|
|                    `rf -t -o example4.pdf -n -g -t $URL`                    |

| ![Example 5](example5-1.jpg) ![Example 5](example5-2.jpg) |
|:---------------------------------------------------------------------------:|
|           `rf -o example5.pdf -n -g -t -r "sub goat's milk" $URL`           |

| ![Example 6](example6-1.jpg) ![Example 6](example6-2.jpg) |
|:---------------------------------------------------------------------------:|
|        `rf -o example6.pdf -n -g -t -r "sub goat's milk" -s 2 $URL`         |