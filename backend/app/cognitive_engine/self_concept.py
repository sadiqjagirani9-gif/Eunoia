def extract(text: str) -> dict:
    markers=('我觉得自己','我是一个','我的优点','我的缺点','我希望成为','我需要改变')
    return {'dimension':'self_concept','self_statements':[text[max(0,text.find(m)):][:180] for m in markers if m in text]}
