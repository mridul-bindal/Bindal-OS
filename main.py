import os
import re 
import time

def tockenize(query:str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", query.lower())

def load_files(path :str) -> dict[str, str]:
    # Placeholder for file  loading logic
    fileNames = os.listdir(path)
    filedata = {}
    for file in fileNames:
        full_path = os.path.join(path, file)
        if os.path.isfile(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                filedata[file] = f.read()
    return filedata

def basic_search(query : str, fileData: dict[str, str]) -> list[str]:
    tokens = set(tockenize(query))
    results = []
    for fileName,file in fileData.items():
        tockenised_file_data = set(tockenize(file))
        if tokens & tockenised_file_data:
            results.append(fileName) 
    return results 
 
def measure_time(func, *args):
    start=time.perf_counter()
    result=func(*args)
    end=time.perf_counter()
    return result,end-start

def main():
    fileData=load_files("data")
    query=" Computer programming course"
    result,time=measure_time(basic_search,query,fileData)
    print(result)
    print(time)

if __name__ == "__main__":
    main()
   