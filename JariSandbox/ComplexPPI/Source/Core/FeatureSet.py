class FeatureSet:    
    def __init__(self, firstNumber=1):
        self.featureIds = {}
        self.firstNumber = firstNumber

    def getId(self, name):
        if not self.featureIds.has_key(name):
            self.featureIds[name] = len(self.featureIds) + self.firstNumber
        return self.featureIds[name]
    
    def write(self, filename):
        f = open(filename, "wt")
        keys = self.featureIds.keys()
        keys.sort()
        for key in keys:
            f.write(str(key)+": "+str(self.featureIds[key])+"\n")
        f.close()
    
    def toStrings(self, rowLength=80):
        strings = [""]
        keys = self.featureIds.keys()
        keys.sort()
        currLen = 0
        for key in keys:
            pair = str(key)+":"+str(self.featureIds[key])
            currLen += len(pair) + 1
            if currLen > rowLength:
                currLen = 0
                strings.append("")
            if strings[-1] != "":
                strings[-1] += ";"
            strings[-1] += pair
        return strings
    
    def load(self, filename):
        self.featureIds = {}
        self.firstNumber = 0
        
        f = open(filename, "rt")
        lines = f.readlines()
        f.close()
        for line in lines:
            key, value = line.split(":")
            key = key.strip()
            value = int(value.strip())
            if self.firstNumber > value:
                self.firstNumber = value
            self.featureIds[key] = value
