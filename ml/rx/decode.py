def best_path(log_probs, charset):
    import numpy as np
    ids=np.asarray(log_probs).argmax(axis=-1).reshape(-1); out=[]; prev=0
    for idx in ids:
        if idx and idx!=prev and idx<len(charset): out.append(charset[idx])
        prev=idx
    return "".join(out)

def beam_search(log_probs, charset, beam_width=10):
    import numpy as np
    arr=np.asarray(log_probs); neg=-float("inf")
    def add(a,b): return float(np.logaddexp(a,b))
    # prefix -> (probability ending in blank, probability ending in non-blank)
    beams={"":(0.,neg)}
    for row in arr:
        next_beams={}
        for prefix,(pb,pnb) in beams.items():
            old_blank,old_nonblank=next_beams.get(prefix,(neg,neg))
            old_blank=add(old_blank,add(pb,pnb)+float(row[0]))
            next_beams[prefix]=(old_blank,old_nonblank)
            for idx in range(1,min(len(row),len(charset))):
                char=charset[idx];score=float(row[idx])
                if prefix.endswith(char):
                    # A repeated character without an intervening blank collapses.
                    ob,on=next_beams.get(prefix,(neg,neg));next_beams[prefix]=(ob,add(on,pnb+score))
                    extension=prefix+char;ob,on=next_beams.get(extension,(neg,neg));next_beams[extension]=(ob,add(on,pb+score))
                else:
                    extension=prefix+char;ob,on=next_beams.get(extension,(neg,neg));next_beams[extension]=(ob,add(on,add(pb,pnb)+score))
        beams=dict(sorted(next_beams.items(),key=lambda item:add(*item[1]),reverse=True)[:beam_width])
    return max(beams,key=lambda prefix:add(*beams[prefix]))
