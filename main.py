import os
import re 
import time

def tokenize(query: str) -> list[str]:
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
        tokens = set(tokenize(file_content))
        for token in tokens:
            inverted_index.setdefault(token, set()).add(file)

    return inverted_index
 
def basic_search(query : str, fileData: dict[str, str]) -> list[str]:
    tokens = set(tokenize(query))
    results = []
    for fileName,file in fileData.items():
        tokenized_file_data = set(tokenize(file))
        if tokens & tokenized_file_data:
            results.append(fileName) 
    return results 
 
def measure_time(func, *args):
    start=time.perf_counter()
    result=func(*args)
    end=time.perf_counter()
    return result,end-start


def  search_with_inverted_index(query:str, inverted_index:dict[str, set[str]]) -> list[str]:
    tokens = set(tokenize(query))
    results = set()
    for token in tokens:
        if token in inverted_index:
            results.update(inverted_index[token])
    return list(results)

def build_ranked_inverted_index(file_data: dict[str, str]) -> dict[str, dict[str, int]]:
    result = {}
    for file_name, file_content in file_data.items():
        tokens = tokenize(file_content)
        for token in tokens:
            if token not in result:
                result[token] = {}
            if file_name not in result[token]:
                result[token][file_name] = 1
            else:
                result[token][file_name] += 1
    return result


def search_ranked_inverted_index(
    query: str, ranked_inverted_index: dict[str, dict[str, int]]
) -> list[str]:
    tokens = set(tokenize(query))
    scores: dict[str,int]={}
    for token in tokens:
        doc_set=ranked_inverted_index.get(token,{})
        for file_name,count in doc_set.items():
            if file_name not in scores:
                scores[file_name]=0
            scores[file_name]+=count

    ranked_docs=sorted(
        scores.items(),
        key= lambda x: x[1],
        reverse=True
    )
    return [doc for doc,score in ranked_docs]

def search_ranked_inverted_index_with_snippets( query: str,ranked_inverted_index: dict[str,dict[str,int]] ,file_data:dict[str,str]) -> list[dict]:
    tokens=set(tokenize(query))
    scores: dict[str,int]={}
    results=[]
    for token in tokens:
        doc_set=ranked_inverted_index.get(token,{})
        for file_name,count in doc_set.items():
            if file_name not in scores:
                scores[file_name]=0
            scores[file_name]+=count

    ranked_docs=sorted(
        scores.items(),
        key= lambda x: x[1],
        reverse=True
    )
    for file_name,score in ranked_docs:
        snippet=create_snippet(file_data[file_name],tokens)
        results.append({
            "file_name":file_name,
            "score":score,
            "snippet":snippet
        })
    return results

def create_snippet( content: str, query_tokens:set[str], max_snippets=3 , snippet_window=100) -> list[str]:
    lower_content=content.lower()
    snippets=[]
    start_pos=0
    for token in query_tokens:
        position=lower_content.find(token,start_pos)
        if(position==-1): continue
        start_pos=max(0,position-snippet_window // 2)
        end_pos= min(len(content),position+snippet_window //2)
        snippet=content[start_pos:end_pos]
        snippet=snippet.replace("\n"," ")
        snippets.append(snippet)
        start_pos=position+len(token)
    
    return snippets[:max_snippets]  

def main():
    fileData=load_files("data")
    query="mongoDB database"
    # result,time=measure_time(basic_search,query,fileData)
    # print(result)
    # print(time)
    inverted_index=build_inverted_index(fileData)
    # print(inverted_index.keys())
    # result2,time2=measure_time(search_with_inverted_index,query,inverted_index)
    # print(result2)
    # print(time2)

    ranked_inverted_index=build_ranked_inverted_index(fileData)
    queries = [
        "MongoDB documents collections",
        "insertOne updateMany deleteOne",
        "compound indexes explain plans",
        "aggregation pipeline match group sort",
        "embedding referencing schema validation",
        "replica set primary secondary write concern",
        "shard key mongos chunks",
        "authentication authorization encryption",
        "backup recovery monitoring replication lag",
    ]
    search_methods={
        # "basic":lambda q:basic_search(q,fileData),
        # "inverted_index": lambda q: search_with_inverted_index(q, inverted_index)
        # "ranked_inverted_index": lambda q: search_ranked_inverted_index(q, ranked_inverted_index),
        "ranked_inverted_index_with_snippets": lambda q: search_ranked_inverted_index_with_snippets(q, ranked_inverted_index,fileData) 
    }
    
    results=[]
    for query in queries:
        print(f"QUERY : {query}")
        for search_method,search_fn in search_methods.items():
            result,time_taken=measure_time(search_fn,query)
            results.append(
                {
                    "method_name":search_method,
                    "result":result,
                    "time_taken":time_taken
                }
            )
            print(f"METHOD_NAME : {search_method}")
            print(f"TIME_TAKEN : {time_taken}")
            print("QUERY :", query)

            for item in result:
                print(f"FILE_NAME : {item['file_name']}")
                # print(f"SCORE : {item['score']}")
                print(f"SNIPPET : {item['snippet']}")
                print("-"*50)
            # print(f"RESULT : {result}")
            # print(f"RESULTS : {results}")
            print("-"*50)



if __name__ == "__main__":
    main()
   
