# <img src='./ui/ytmus.png' width='50' height='50' style='vertical-align:bottom'/> Youtube Music Skill

Youtube Music OCP Skill

## About

search Youtube Music by voice!

![](./gui.gif)

## Examples

* "play António Variações"

## Settings

you can add queries to skill settings that will then be pre-fetched on skill load

this populates the featured_media entries + provides fast matching against cached entries

```javascript
{    
"featured":  ["zz top", "ai covers", "frank sinatra"]
}
```

a local cache of entries can be found at `~/.cache/OCP/Youtube.json`


## Credits
JarbasAl

## Category
**Entertainment**

## Tags
- youtube
- common play
- music
