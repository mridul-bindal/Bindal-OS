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

def build_inverted_index(file_data: dict[str, str]) -> dict[str, set[str]]:
    inverted_index = {}

    for file, file_content in file_data.items():
        tokens = set(tockenize(file_content))
        for token in tokens:
            inverted_index.setdefault(token, set()).add(file)

    return inverted_index
 
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


def  search_with_inverted_index(query:str, inverted_index:dict[str, set[str]]) -> list[str]:
    tokens = set(tockenize(query))
    results = set()
    for token in tokens:
        if token in inverted_index:
            results.update(inverted_index[token])
    return list(results)

def main():
    fileData=load_files("data")
    query="mongoDB database"
    result,time=measure_time(basic_search,query,fileData)
    print(result)
    print(time)
    inverted_index=build_inverted_index(fileData)
    # print(inverted_index.keys())
    result2,time2=measure_time(search_with_inverted_index,query,inverted_index)
    print(result2)
    print(time2)



if __name__ == "__main__":
    main()
   