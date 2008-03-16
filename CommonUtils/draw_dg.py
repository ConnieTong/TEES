import cElementTree as ET
import cElementTreeUtils as ETUtils
import sys
import re

class SVGOptions:

    fontSize=24
    labelFontSize=20
    tokenSpace=10 #horizontal space between tokens
    depVertSpace=20
    minDepPadding=10 #How many points, at least, should be reserved horizontally for the dependency rounded corner

def strint(i):
    return str(int(i))

def textWidth(txt,fontSize):
    return len(txt)*fontSize*0.65

tokenSpec=re.compile(r"^(.*)_([0-9]+)$")
def tokSpec(tokTxt):
    match=tokenSpec.match(tokTxt)
    if match:
        return match.group(1),match.group(2)
    else:
        return tokTxt,None

class Token:

    def __init__(self,txt,pos):
        
        self.txt,self.spec=tokSpec(txt)
        self.pos=pos
        self.x=0#layout() fills this
        self.y=0#layout() fills this
        self.styleDict={"text-anchor":"middle",
                    "fill":"black"}

    def matches(self,txt,spec):
        return self.txt==txt and self.spec==spec

    def width(self):
        return textWidth(self.txt,SVGOptions.fontSize)

    def toSVG(self):
        node=ET.Element("text")
        node.set("systemLanguage","en")
        node.set("x",strint(self.x))
        node.set("y",strint(self.y))
        node.set("font-size",strint(SVGOptions.fontSize))
        node.set("font-family","monospace")
        styleStr=";".join("%s:%s"%(var,val) for var,val in self.style().items())
        node.set("style",styleStr)
        node.text=self.txt
        return [node]

    def style(self):
        return self.styleDict


class Dep:

    #Makes dependency from tok1 to tok2
    def __init__(self,tok1,tok2,dType):
        self.tok1=tok1
        self.tok2=tok2
        if tok1.pos>tok2.pos:
            raise ValueError("Dep should always have tokens in linear order and no self dependencies: %d-%d %s %s %s"%(tok1.pos,tok2.pos,tok1.txt,tok2.txt,dType))
        self.type=dType
        self.height=0#layout() fills this
        #default style
        self.arcStyleDict={"fill":"none",
                       "stroke":"black",
                       "stroke-width":"1"}
        self.labelStyleDict={"text-anchor":"middle",
                            "fill":"black"}

    def minWidth(self):
        return textWidth(self.type,SVGOptions.labelFontSize)+2*SVGOptions.minDepPadding

    def computeParameters(self):
        y=self.tok1.y-SVGOptions.fontSize
        frox=self.tok1.x
        tox=self.tok2.x
        corner1x,corner1y=frox,y-self.height*SVGOptions.depVertSpace
        corner2x,corner2y=tox,y-self.height*SVGOptions.depVertSpace
        c1bx,c1by=corner1x,corner1y #Top left control point, beginning
        c1ex,c1ey=corner1x,corner1y
        c2bx,c2by=corner2x,corner2y
        c2ex,c2ey=corner2x,corner2y
        linebx=frox
        lineex=tox
        lineby=corner1y+(y-corner1y)*0.6
        lineey=lineby
        midx,midy=frox+(tox-frox)//2,y-self.height*SVGOptions.depVertSpace
        self.param={'frox':frox,
                    'y':y,
                    'c1bx':c1bx,
                    'c1by':c1by,
                    'c1ex':c1ex,
                    'c1ey':c1ey,
                    'midx':midx,
                    'midy':midy,
                    'c2bx':c2bx,
                    'c2by':c2by,
                    'c2ex':c2ex,
                    'c2ey':c2ey,
                    'tox':tox,
                    'linebx':linebx,
                    'lineby':lineby,
                    'lineex':lineex,
                    'lineey':lineey}

    def arcSVG(self):
        
        spec="M%(frox)d,%(y)d L%(linebx)d,%(lineby)d C%(c1bx)d,%(c1by)d %(c1ex)d,%(c1ey)d %(midx)d,%(midy)d C%(c2bx)d,%(c2by)d %(c2ex)d,%(c2ey)d %(lineex)d,%(lineey)d L%(tox)d,%(y)d"%self.param
        arcN=ET.Element("path")
        arcN.set("d",spec)
        styleStr=";".join("%s:%s"%(var,val) for var,val in self.arcStyle().items())
        arcN.set("style",styleStr)
        #pathStr='<path d=%(spec)s style="fill:none;%(style)s"/>'%{'spec':spec,'style':highlightToStyle('depLine',highlight)}
        return [arcN]

    def labelSVG(self):
            textW=textWidth(self.type,SVGOptions.labelFontSize)
            textH=SVGOptions.labelFontSize
            txtX,txtY=self.param["midx"],self.param["midy"]+textH/2-4

            recNode=ET.Element("rect")
            recNode.set("x",strint(txtX-textW/2-1))
            recNode.set("y",strint(self.param["midy"]-2))
            recNode.set("width",strint(textW+4))
            recNode.set("height",strint(4))
            recNode.set("style","fill:white")
            
            labNode=ET.Element("text")
            labNode.set("systemlanguage","en")
            labNode.set("x",strint(txtX))
            labNode.set("y",strint(txtY))
            labNode.set("txt",self.type)
            labNode.set("font-size",strint(SVGOptions.labelFontSize))
            labNode.set("font-family","monospace")
            labNode.text=self.type
            styleStr=";".join("%s:%s"%(var,val) for var,val in self.labelStyle().items())
            labNode.set("style",styleStr)
            return [recNode,labNode]

    def arcStyle(self):
        return self.arcStyleDict

    def labelStyle(self):
        return self.labelStyleDict


def simpleTokenLayout(tokens,dependencies,baseY):
    #First a simple, initial layout for the tokens
    widths=[t.width() for t in tokens]
    
    y=baseY
    tokens[0].x=widths[0]//2
    tokens[0].y=y
    for idx in range(1,len(tokens)):
        tokens[idx].x=tokens[idx-1].x+widths[idx-1]//2+SVGOptions.tokenSpace+widths[idx]//2
        tokens[idx].y=y

#nudges tokens, taking into account dependencies on one level
def nudgeTokens(tokens,deps):
    deps.sort(cmp=lambda a,b: cmp(a.tok1.pos,b.tok1.pos)) #we have dependencies on one level, no ties should happen!
    nudge=[0 for t in tokens]
    for d in deps:
        currentDX=d.tok2.x - d.tok1.x
        minW=d.minWidth()
        if minW>currentDX: #need to nudge token2 a bit to the right
            nudge[d.tok2.pos]=minW-currentDX
    #now apply the nudge
    cumulative=0
    for idx,nudgeX in enumerate(nudge):
        cumulative+=nudgeX
        tokens[idx].x+=cumulative

#calls nudgeTokens() one layer at a time
def improveTokenLayout(tokens,dependencies):
    dependencies.sort(cmp=lambda a,b:cmp(a.height,b.height))
    #gather height breaks
    breaks=[]
    for idx in range(1,len(dependencies)):
        if dependencies[idx].height!=dependencies[idx-1].height:
            breaks.append(idx-1)
    breaks=[0]+breaks+[len(dependencies)-1]
    for idx in range(1,len(breaks)):
        nudgeTokens(tokens,dependencies[breaks[idx-1]:breaks[idx]+1])
        

def depCMP(a,b):
    aLen=a.tok2.pos-a.tok1.pos
    bLen=b.tok2.pos-b.tok1.pos
    if aLen!=bLen:
        return cmp(aLen,bLen)
    else:
        return cmp(a.tok1.pos,b.tok1.pos)

def depHeights(tokenCount,deps):
    heights=[0 for x in range(tokenCount-1)]
    deps.sort(cmp=depCMP)
    for dep in deps:
        maxH=max(heights[tPos] for tPos in range(dep.tok1.pos,dep.tok2.pos))
        dep.height=maxH+1
        for tPos in range(dep.tok1.pos,dep.tok2.pos):
            heights[tPos]=maxH+1
    return max(heights)

def drawOrder(a,b):
    if a.tag!=b.tag:
        if a.tag=="path": #always draw the arcs first
            return -1
        if a.tag=="text": #always draw text last
            return +1
        assert a.tag=="rect", a.tag
        if b.tag=="path":
            return +1
        if b.tag=="text":
            return -1
        assert False
    else:
        return 0
    
def generateSVG(tokens,dependencies):
    layout(tokens,dependencies)
    tree=ET.Element("svg")
    tree.set("xmlns","http://www.w3.org/2000/svg")
    tree.set("xmlns:xlink","http://www.w3.org/1999/xlink")
    tree.set("version","1.1")
    tree.set("baseProfile","full")
    allNodes=[]
    for t in tokens:
        allNodes.extend(t.toSVG())
    for d in dependencies:
        allNodes.extend(d.arcSVG())
        allNodes.extend(d.labelSVG())
    allNodes.sort(cmp=drawOrder)
    for n in allNodes:
        tree.append(n)
    return tree

#The main layout function -> fills in all the parameters needed to draw the tree
def layout(tokens,deps):
    maxHeight=depHeights(len(tokens),deps)
    baseY=SVGOptions.fontSize+maxHeight*SVGOptions.depVertSpace+SVGOptions.labelFontSize//2+5
    simpleTokenLayout(tokens,deps,baseY)
    improveTokenLayout(tokens,deps)
    for dep in deps:
        dep.computeParameters()


def readInput(lines):
    tokens=None
    deps=[]
    tokensRead=False
    for line in lines:
        line=line.strip()
        if not line or line[0]=="#":
            continue
        if not tokensRead: #We have the tokens
            tokensRead=True
            tokens=[Token(txt,idx) for (idx,txt) in enumerate(line.split())]
        else: #we have a dependency
            try:
                t1,dType,t2=line.split()
            except ValueError:
                raise ValueError("This is not a dependency line: %s"%line)
            t1txt,t1spec=tokSpec(t1)
            matching1=[tok for tok in tokens if tok.matches(t1txt,t1spec)]
            if len(matching1)!=1:
                raise ValueError("I have %d candidates for %s in dependency \"%s\""%(len(matching1),t1,line))
            t2txt,t2spec=tokSpec(t2)
            matching2=[tok for tok in tokens if tok.matches(t2txt,t2spec)]
            if len(matching2)!=1:
                raise ValueError("I have %d candidates for %s in dependency \"%s\""%(len(matching2),t2,line))
            tok1=matching1[0]
            tok2=matching2[0]
            deps.append(Dep(tok1,tok2,dType))
    if len(deps)==0:
        raise ValueError("Zero dependencies read!")
    return tokens,deps
                                 
        
    

if __name__=="__main__":
    import optparse
    desc=\
"""A program for plotting dependency structures into SVG.

cat dependencies | python draw_dg.py > dependencies.svg

The format of the dependency file is specified in example.dep
To get a PDF version of the plot, use the script svg2pdf.sh as follows:

cat dependencies | python draw_dg.py | ./svg2pdf.sh > dependencies.pdf

For this to work, you need inkscape, pdf2ps, ps2epsi, and epstopdf. See
the script svg2pdf for details if needed.
"""
    parser=optparse.OptionParser(usage=desc)
    (options,args)=parser.parse_args()
    tokens,deps=readInput(sys.stdin)
    t=generateSVG(tokens,deps)
    ETUtils.write(t,sys.stdout)
    print
