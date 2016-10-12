package main

import "crypto/rand"
import "github.com/Psiphon-Inc/crypto/nacl/box"
import "fmt"
import "encoding/base64"
import "encoding/json"

func main() {

	pubkey, privkey, _ := box.GenerateKey(rand.Reader)

	var publicKey, privateKey []byte

	publicKey = (*pubkey)[0:32]
	privateKey = (*privkey)[0:32]

	m := map[string]string{"publicKey": base64.StdEncoding.EncodeToString(publicKey),
		"privateKey": base64.StdEncoding.EncodeToString(privateKey)}

	j, _ := json.Marshal(m)
	fmt.Printf(string(j))
	return
}
